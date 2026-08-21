# robot.py - Reachy Mini as the narrator's face and voice.
#
# WHAT THIS IS FOR
# The game already worked with a disembodied voice. The robot adds a thing for
# the children to look at while that voice talks: a head that turns towards
# them, antennas that perk up when a challenge opens and droop when it is
# failed. It scores nothing. Every answer still comes from a wand over radio.
#
# That is deliberate. If the robot is unplugged, missing, or its SDK is not
# installed, every method here quietly becomes a no-op and the session runs
# exactly as it did before. Nothing in engine.py, no content pack and no wand
# firmware knows whether a robot is present.
#
# THREE THINGS THE SDK GIVES US NEARLY FREE
#   - enable_wobbling(): audio played through the robot is analysed and turned
#     into head movement, so narration animates itself. We render no motion.
#   - look_at_image(u, v): a camera pixel converted straight to a head pose,
#     which is the whole of tracker.py's job (see that file).
#   - play_sound(): plays a WAV on the robot's speaker.
#
# THE AWKWARD BIT: play_sound IS FIRE AND FORGET
# It returns immediately and never reports completion, but the engine needs
# say() to block for the length of a line or the pacing collapses. So we read
# the duration out of the WAV header ourselves and wait that long. The files
# are all local and pre-rendered, so this is exact rather than a guess.
#
# The same limitation means a line in progress cannot be cut short. That is
# survivable because the engine only ever goes quiet AFTER a line has finished,
# but it does mean the gamemaster's stop button takes effect at the end of the
# current sentence rather than instantly.

import os
import threading
import time
import wave

import config

try:
    import numpy as np
    from reachy_mini import ReachyMini
    from reachy_mini.utils import create_head_pose
    _SDK_ERROR = None
except Exception as exc:            # ImportError, but the SDK also pulls in
    np = None                       # GStreamer bindings that fail noisily
    ReachyMini = None
    create_head_pose = None
    _SDK_ERROR = str(exc)


# ---------------------------------------------------------------------------
# Expressions
#
# Each is a list of steps, played in order on a background thread so the
# scenario never waits for the robot to finish pulling a face. Head values are
# millimetres and degrees; antennas are degrees, both the same sign to move
# symmetrically ("out" is positive).
#
# Keep these small. A narrator that lunges about is harder to listen to, and
# every degree of head movement is servo noise the wands' microphones hear.
# ---------------------------------------------------------------------------
NEUTRAL = {'head': {}, 'antennas': 0, 'duration': 0.6, 'method': 'minjerk'}

EXPRESSIONS = {
    # Attention: chin up, antennas out. Played as a challenge opens, so the
    # children get a visual "go" a beat before their wands light up.
    'listen': [
        {'head': {'pitch': -8, 'z': 6}, 'antennas': 45,
         'duration': 0.35, 'method': 'ease_in_out'},
    ],

    # Narrating: a small lean in. The wobbler supplies the actual talking
    # motion on top of this pose.
    'tell': [
        {'head': {'pitch': -3, 'x': 5}, 'antennas': 15,
         'duration': 0.5, 'method': 'minjerk'},
    ],

    # Verdicts. 'cartoon' interpolation overshoots slightly, which reads as
    # delight rather than as a servo moving.
    'pass': [
        {'head': {'pitch': 14, 'z': -4}, 'antennas': 70,
         'duration': 0.22, 'method': 'cartoon'},
        {'head': {'pitch': -10, 'z': 8}, 'antennas': 20,
         'duration': 0.28, 'method': 'cartoon'},
        dict(NEUTRAL, duration=0.4),
    ],
    'fail': [
        {'head': {'pitch': 16, 'z': -8}, 'antennas': -45,
         'duration': 0.7, 'method': 'ease_in_out'},
        {'head': {'pitch': 10, 'z': -5}, 'antennas': -30,
         'duration': 0.9, 'method': 'minjerk'},
    ],

    # A slow look side to side, for the pause while a pack loads or between
    # scenes. Keeps the robot from looking switched off.
    'think': [
        {'head': {'yaw': 18, 'roll': 5}, 'antennas': 10,
         'duration': 0.8, 'method': 'minjerk'},
        {'head': {'yaw': -18, 'roll': -5}, 'antennas': 10,
         'duration': 1.1, 'method': 'minjerk'},
        dict(NEUTRAL, duration=0.8),
    ],

    'neutral': [NEUTRAL],
}


def wav_seconds(path):
    """
    How long a WAV lasts, straight out of its header.

    Returns None if the file is missing or is not a WAV we can read, which the
    caller treats as "fall back to estimating from the word count".
    """
    try:
        with wave.open(path, 'rb') as handle:
            rate = handle.getframerate()
            if not rate:
                return None
            return handle.getnframes() / float(rate)
    except Exception:
        return None


class Robot(object):
    """
    A Reachy Mini, or a convincing impression of nothing at all.

    Every public method is safe to call when the robot is disabled, absent or
    broken. Check .ready if you want to know which you have.
    """

    def __init__(self, enabled=None):
        self.enabled = config.USE_ROBOT if enabled is None else enabled
        self.ready = False
        self.error = None
        self.mini = None

        # Basename of every WAV already sent to the robot. Playing a local path
        # over the network re-uploads it every time; playing a bare filename
        # the robot already holds does not.
        self._uploaded = {}

        # Motion commands block for their duration, and three things want to
        # move the head: narration expressions, the camera tracker, and the
        # gamemaster. This lock arbitrates. The tracker only ever TRIES for it
        # and skips its turn if something better is using the head.
        self._motion_lock = threading.Lock()

        # Set while a microphone challenge is open. The head must be still:
        # servo noise is picked up by the wands as easily as a clap is.
        self._still = threading.Event()

        self._expression = None

        if not self.enabled:
            return
        if ReachyMini is None:
            self.error = 'reachy_mini SDK not installed ({})'.format(_SDK_ERROR)
            return

        try:
            self.mini = ReachyMini(
                host=config.ROBOT_HOST,
                port=config.ROBOT_PORT,
                connection_mode=config.ROBOT_CONNECT_MODE,
                timeout=config.ROBOT_TIMEOUT_S,
            )
            self.ready = True
        except Exception as exc:
            self.error = 'could not reach {}: {}'.format(config.ROBOT_HOST, exc)
            return

        try:
            self.mini.wake_up()
            if config.ROBOT_WOBBLE:
                self.mini.enable_wobbling()
        except Exception as exc:
            # Connected but unhappy. Worth reporting, not worth refusing to
            # play: a robot that will not nod is still a robot that can talk.
            self.error = 'connected, but setup failed: {}'.format(exc)

    # =======================================================================
    # Narration
    # =======================================================================
    def can_speak(self):
        return bool(self.ready and config.ROBOT_NARRATES)

    def preload(self, paths):
        """
        Push narration WAVs to the robot ahead of the session.

        Returns how many are now resident. Uploading 60 short files takes a few
        seconds once, against a stall on every unheard line if we do not.
        """
        if not self.can_speak():
            return 0
        count = 0
        for path in paths:
            if self._resident_name(path):
                count += 1
        return count

    def speak(self, path, wait=True, stop_event=None):
        """
        Play one narration WAV. Returns False if the caller should fall back to
        its own audio, True if the robot has it in hand.
        """
        if not self.can_speak() or not os.path.exists(path):
            return False

        name = self._resident_name(path) or os.path.abspath(path)
        try:
            self.mini.media.play_sound(name)
        except Exception as exc:
            self.error = 'play_sound failed: {}'.format(exc)
            return False

        self.express('tell')
        if wait:
            seconds = wav_seconds(path)
            if seconds is not None:
                self._sleep(seconds + config.ROBOT_SPEAK_PAD_S, stop_event)
        return True

    def silence(self):
        """
        Best effort: stop whatever is playing.

        play_sound offers no interrupt, so this may not cut a line already in
        flight. The engine does not rely on it - it lets lines finish before a
        microphone challenge - but the stop button should try.
        """
        if not self.ready:
            return
        try:
            self.mini.media.stop_playing()
        except Exception:
            pass

    def _resident_name(self, path):
        """
        Ensure the robot holds this WAV and return the name to play it by, or
        None if it must be played from a local path instead.
        """
        path = os.path.abspath(path)
        if path in self._uploaded:
            return self._uploaded[path]
        if not os.path.exists(path):
            return None

        # upload_sound lives on the audio backend, and only the networked one
        # implements it - running on the robot itself it is a no-op, because
        # the file is already reachable.
        audio = getattr(self.mini.media, 'audio', None)
        upload = getattr(audio, 'upload_sound', None)
        if upload is None:
            return None
        try:
            upload(path)
        except Exception:
            return None

        name = os.path.basename(path)
        self._uploaded[path] = name
        return name

    # =======================================================================
    # Movement
    # =======================================================================
    def express(self, name):
        """
        Start an expression. Returns immediately; the movement runs on its own
        thread so a nod never delays the next narration line.
        """
        if not self.ready or not config.ROBOT_EMOTES:
            return
        steps = EXPRESSIONS.get(name)
        if steps is None:
            return
        if self._still.is_set():
            return                  # a microphone window is open, stay quiet

        # One expression at a time. A new one supersedes an unfinished one
        # rather than queueing behind it - the current moment matters more than
        # finishing the last reaction.
        if self._expression is not None and self._expression.is_alive():
            return

        self._expression = threading.Thread(
            target=self._play_expression, args=(steps,), daemon=True)
        self._expression.start()

    def _play_expression(self, steps):
        if not self._motion_lock.acquire(timeout=1.0):
            return
        try:
            for step in steps:
                if self._still.is_set():
                    return
                self._goto(step)
        finally:
            self._motion_lock.release()

    def _goto(self, step):
        try:
            head = create_head_pose(mm=True, degrees=True, **step.get('head', {}))
            antenna = float(step.get('antennas', 0))
            self.mini.goto_target(
                head=head,
                antennas=np.deg2rad([antenna, antenna]),
                duration=step.get('duration', 0.5),
                method=step.get('method', 'minjerk'),
            )
        except Exception as exc:
            self.error = 'movement failed: {}'.format(exc)

    def look_at_pixel(self, u, v, duration=None):
        """
        Turn the head towards a point in the camera image.

        Returns False when the head is busy or held still, so the tracker knows
        its request was dropped and can simply try again with a fresher frame
        instead of queueing a move to where somebody used to be.
        """
        if not self.ready or self._still.is_set():
            return False
        if not self._motion_lock.acquire(blocking=False):
            return False
        try:
            self.mini.look_at_image(
                int(u), int(v),
                duration=config.TRACKER_LOOK_S if duration is None else duration,
            )
            return True
        except Exception as exc:
            self.error = 'look_at_image failed: {}'.format(exc)
            return False
        finally:
            self._motion_lock.release()

    def grab_frame(self):
        """One camera frame as a BGR numpy array, or None."""
        if not self.ready:
            return None
        try:
            return self.mini.media.get_frame()
        except Exception:
            return None

    def camera_size(self):
        """(width, height) of the camera image, or None if there is no camera."""
        if not self.ready:
            return None
        try:
            return tuple(self.mini.media.camera.resolution)
        except Exception:
            return None

    # =======================================================================
    # Holding still for microphone challenges
    # =======================================================================
    def hold_still(self):
        """
        Stop moving and stay stopped until release().

        CLAP and SHOUT are scored by the microphones on the wands, which hear
        servo whine perfectly well. The engine already silences narration
        before those windows; this silences the robot's body too.
        """
        self._still.set()
        self.silence()

    def release(self):
        self._still.clear()

    def is_held_still(self):
        return self._still.is_set()

    # =======================================================================
    # Housekeeping
    # =======================================================================
    def _sleep(self, seconds, stop_event):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                return
            time.sleep(0.03)

    def describe(self):
        if not self.enabled:
            return 'robot off in config.py'
        if not self.ready:
            return 'no robot ({})'.format(self.error or 'unknown reason')
        voice = 'narrating' if config.ROBOT_NARRATES else 'silent'
        if self.error:
            return 'robot {} - warning: {}'.format(voice, self.error)
        return 'robot {}'.format(voice)

    def close(self):
        if not self.ready:
            return
        try:
            # goto_sleep folds the head down to a defined resting pose, so
            # there is no point queueing an expression behind it.
            self.mini.goto_sleep()
        except Exception:
            pass
        try:
            self.mini.__exit__(None, None, None)
        except Exception:
            pass
        self.ready = False
