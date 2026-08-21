# audio.py - narration and sound effects for the gamemaster station.
#
# Narration is NOT synthesised at runtime. tools/build_voice.py renders every
# line to a WAV ahead of time and this module only plays files back, which is
# why the whole thing still works on a Raspberry Pi B+ that could never run a
# speech engine live.
#
# There are three places narration can come out of, tried in this order:
#   - a Reachy Mini, if one is connected and config.ROBOT_NARRATES is on
#   - pygame, through the computer's own speakers
#   - the terminal, printed
#
# So it degrades in useful steps:
#   - no robot, or robot narration turned off  -> pygame
#   - no pygame installed, or no audio device  -> lines are printed instead
#   - working output but a WAV missing         -> that line is printed instead
# In every case the pause is still taken, at roughly reading speed, so the
# pacing of a session does not fall apart just because the voices are not
# built yet. You can rehearse a whole scenario silently.

import os
import time

try:
    import pygame
    _PYGAME_ERROR = None
except ImportError as exc:
    pygame = None
    _PYGAME_ERROR = str(exc)

import config

# Silent fallback pacing. Read aloud, English runs about 2.5 words a second.
WORDS_PER_SECOND = 2.5
MIN_SILENT_PAUSE = 0.8


class Audio(object):

    def __init__(self, pack_id, enabled=None, robot=None):
        self.pack_id = pack_id
        self.enabled = config.AUDIO_ENABLED if enabled is None else enabled
        self.error = None
        self.robot = robot
        self._sounds = {}
        self._voice = None
        self._sfx = None
        self.ready = False

        if not self.enabled:
            return
        if pygame is None:
            self.error = 'pygame not installed ({})'.format(_PYGAME_ERROR)
            return

        try:
            pygame.mixer.init()
            # Separate channels so a sound effect never cuts the narrator off.
            pygame.mixer.set_num_channels(4)
            self._voice = pygame.mixer.Channel(0)
            self._sfx = pygame.mixer.Channel(1)
            self._voice.set_volume(config.NARRATION_VOLUME)
            self._sfx.set_volume(config.SFX_VOLUME)
            self.ready = True
        except Exception as exc:
            self.error = 'no audio device: {}'.format(exc)

    # -- paths -------------------------------------------------------------
    def voice_path(self, line_id):
        return os.path.join(config.VOICE_DIR, self.pack_id,
                            '{}.wav'.format(line_id))

    def sfx_path(self, name):
        return os.path.join(config.SFX_DIR, '{}.wav'.format(name))

    def missing_lines(self, line_ids):
        """Which lines have no WAV yet. The GM console shows this as a warning."""
        return [lid for lid in line_ids if not os.path.exists(self.voice_path(lid))]

    def preload(self, line_ids):
        """
        Send this pack's narration to the robot before the session starts.

        Playing a file the robot does not hold uploads it first, so without
        this the first airing of every line stalls for the transfer - exactly
        when a room full of children is waiting for it.
        """
        if not self._robot_speaks() or not config.ROBOT_PRELOAD_VOICES:
            return 0
        paths = [self.voice_path(lid) for lid in line_ids]
        return self.robot.preload(p for p in paths if os.path.exists(p))

    def _robot_speaks(self):
        return self.robot is not None and self.robot.can_speak()

    # -- playback ----------------------------------------------------------
    def _load(self, path):
        if path in self._sounds:
            return self._sounds[path]
        if not self.ready or not os.path.exists(path):
            return None
        try:
            sound = pygame.mixer.Sound(path)
        except Exception:
            sound = None
        self._sounds[path] = sound
        return sound

    def say(self, line_id, text='', wait=True, stop_event=None):
        """
        Speak one narration line. Returns when it has finished if wait is True.
        stop_event lets the gamemaster's stop button cut a long line short.
        """
        path = self.voice_path(line_id)

        # The robot takes priority when it has the file. It returns False if it
        # cannot - no robot, narration turned off, WAV missing - and we drop
        # through to the computer's own speakers without noticing the
        # difference.
        if self._robot_speaks() and self.robot.speak(
                path, wait=wait, stop_event=stop_event):
            return

        sound = self._load(path)

        if sound is None:
            # No file: show the words and hold for about as long as reading
            # them aloud would take.
            if text:
                print('[narrator] {}'.format(text))
            if wait:
                self._silent_pause(text, stop_event)
            return

        self._voice.play(sound)
        if wait:
            self._wait_for(self._voice, stop_event)

    def sfx(self, name, wait=False, stop_event=None):
        if not name:
            return

        # A roar or an alarm belongs in the room, not inside a small robot, so
        # effects stay on the computer's speakers whenever it has any. Only if
        # pygame is unavailable do we ask the robot to carry them.
        if not self.ready and self._robot_speaks():
            if self.robot.speak(self.sfx_path(name), wait=wait,
                                stop_event=stop_event):
                return

        sound = self._load(self.sfx_path(name))
        if sound is None:
            print('[sfx] {}'.format(name))
            return
        self._sfx.play(sound)
        if wait:
            self._wait_for(self._sfx, stop_event)

    def stop(self):
        """Cut all sound immediately. Used before microphone challenges."""
        if self._robot_speaks():
            # Best effort only: the robot's player cannot interrupt a line in
            # flight. It does not matter for microphone challenges, because the
            # engine only goes quiet once a line has finished.
            self.robot.silence()
        if not self.ready:
            return
        try:
            self._voice.stop()
            self._sfx.stop()
        except Exception:
            pass

    def is_talking(self):
        if not self.ready:
            return False
        try:
            return bool(self._voice.get_busy())
        except Exception:
            return False

    def go_quiet(self, lead=None):
        """
        Silence everything and hold, so the wands' microphones are not still
        hearing the narrator when a CLAP or SHOUT window opens.
        """
        self.stop()
        time.sleep(config.MIC_QUIET_LEAD_S if lead is None else lead)

    # -- internals ---------------------------------------------------------
    def _wait_for(self, channel, stop_event):
        while True:
            try:
                if not channel.get_busy():
                    return
            except Exception:
                return
            if stop_event is not None and stop_event.is_set():
                self.stop()
                return
            time.sleep(0.03)

    def _silent_pause(self, text, stop_event):
        words = len(text.split()) if text else 0
        seconds = max(MIN_SILENT_PAUSE, words / WORDS_PER_SECOND)
        deadline = time.time() + seconds
        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                return
            time.sleep(0.05)

    def describe(self):
        if not self.enabled:
            return 'audio disabled in config.py'
        if self._robot_speaks():
            return 'narration on the robot, effects {}'.format(
                'on this computer' if self.ready else 'on the robot too')
        if self.ready:
            return 'audio ready'
        return 'silent mode ({})'.format(self.error or 'unknown reason')
