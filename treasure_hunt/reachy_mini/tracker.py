# tracker.py - the robot watches the room.
#
# TREASURE HUNT REACHY MINI — this file runs ON the robot (CM4).
# It is a verbatim copy of quest_engine/computer_app/tracker.py.
# agent.py injects the `config` module into sys.modules before importing this.
#
# WHAT IT DOES, AND WHAT IT DELIBERATELY DOES NOT
# It finds a person in the camera image and turns the robot's head towards
# them. That is all. It scores nothing, it answers nothing, and no verb, pack
# or wand depends on it. If it fails you get an inattentive robot, not a broken
# game - which is why it is worth having before any camera-scored challenge is.
#
# Scoring by camera would need to know WHICH child did something, and the
# camera cannot tell you that: the wire protocol is per-player (A|<pid>|...)
# and a face is not a player id. Solving that needs children on numbered floor
# spots, or group-only verbs that need no attribution at all. Neither is here.
#
# THE ONE GENUINELY AWKWARD THING: THE CAMERA IS IN THE HEAD
# Turning to look at a child moves the camera that spotted them, so the image
# is not a fixed frame of reference and every move invalidates the next frame.
# Two consequences run through the code below:
#
#   - After a move we ignore frames for TRACKER_SETTLE_S, otherwise the robot
#     chases the apparent motion it caused itself and drifts off across the
#     room.
#   - Frame-differencing only runs when the head has been still a while. With
#     a moving camera every pixel differs and the whole frame reads as motion.
#
# DETECTION, IN TWO TIERS
#   1. Faces, via OpenCV's stock Haar cascade. Reliable when a child is facing
#      the robot, which during narration is most of the time.
#   2. Failing that, movement. Children in profile or looking at their wands
#      are invisible to a frontal face detector but they are rarely still.

import threading
import time

import config

try:
    import cv2
    _CV_ERROR = None
except Exception as exc:
    cv2 = None
    _CV_ERROR = str(exc)

# Detection runs on a downscaled copy. Faces of children a few metres away are
# still tens of pixels across at this width, and it keeps a Pi comfortable.
WORK_WIDTH = 320

# Movement smaller than this fraction of the frame is noise - a curtain, a
# flickering screen, compression artefacts.
MOTION_MIN_AREA_FRAC = 0.004

# How long the head must have been still before frame-differencing is trusted.
MOTION_NEEDS_STILL_S = 1.2


class Tracker(object):
    """
    Drives a Robot's gaze from its own camera. Start it and forget it.

    Safe to construct when disabled, when OpenCV is missing, or when the robot
    never connected: it simply never starts a thread.
    """

    def __init__(self, robot, enabled=None):
        self.robot = robot
        self.enabled = config.USE_TRACKER if enabled is None else enabled
        self.error = None
        self.running = False

        self._thread = None
        self._stop = threading.Event()
        self._paused = threading.Event()

        self._cascade = None
        self._prev_gray = None
        self._last_move_at = 0.0
        self._last_seen_at = 0.0
        self._last_idle_at = 0.0
        self._looks = 0
        self._mode = 'idle'         # what it last tracked on: face, motion, idle

        if not self.enabled:
            return
        if cv2 is None:
            self.error = 'opencv not installed ({})'.format(_CV_ERROR)
            return
        if not getattr(robot, 'ready', False):
            self.error = 'no robot to drive'
            return

        try:
            path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            cascade = cv2.CascadeClassifier(path)
            if cascade.empty():
                raise RuntimeError('cascade file is empty: {}'.format(path))
            self._cascade = cascade
        except Exception as exc:
            # Not fatal. Movement tracking alone still looks alive.
            self.error = 'no face detector ({}), movement only'.format(exc)

    # =======================================================================
    # Lifecycle
    # =======================================================================
    def start(self):
        if not self.enabled or not getattr(self.robot, 'ready', False):
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.running = True
        return True

    def stop(self):
        self._stop.set()
        self.running = False

    def pause(self):
        """Stop looking around, without tearing the camera down."""
        self._paused.set()

    def resume(self):
        self._paused.clear()
        self._prev_gray = None      # the view may have moved while we were out

    # =======================================================================
    # The loop
    # =======================================================================
    def _loop(self):
        period = 1.0 / max(1.0, config.TRACKER_FPS)

        while not self._stop.is_set():
            time.sleep(period)

            if self._paused.is_set() or self.robot.is_held_still():
                continue

            frame = self.robot.grab_frame()
            if frame is None:
                continue

            try:
                self._consider(frame)
            except Exception as exc:
                self.error = str(exc)

    def _consider(self, frame):
        """
        Decide what to do about one frame, and do it.

        Everything that decides whether to move lives in here rather than in
        the loop above, so the rules can be tested by handing it frames -
        see tools/simulate_robot.py.
        """
        # The head is still finishing its last move, so this frame shows a
        # sliding view. Anything measured on it would describe our own movement
        # rather than the children's.
        if time.time() - self._last_move_at < config.TRACKER_SETTLE_S:
            self._prev_gray = None
            return

        height, width = frame.shape[:2]
        scale = WORK_WIDTH / float(width) if width > WORK_WIDTH else 1.0
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1.0 else frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        target = self._find_face(gray, scale)
        mode = 'face'

        if target is None:
            target = self._find_movement(gray, scale)
            mode = 'motion'

        self._prev_gray = gray

        if target is None:
            self._maybe_idle()
            return

        self._last_seen_at = time.time()
        self._mode = mode

        # Already looking near enough at them. Chasing sub-deadzone error makes
        # the robot twitch continuously, which reads as broken rather than
        # attentive.
        u, v = target
        if abs(u - width / 2.0) < config.TRACKER_DEADZONE_PX and \
           abs(v - height / 2.0) < config.TRACKER_DEADZONE_PX:
            return

        # look_at_image rejects the extreme edges of the image, so keep the
        # request just inside them.
        u = int(min(max(u, 2), width - 2))
        v = int(min(max(v, 2), height - 2))

        if self.robot.look_at_pixel(u, v):
            self._last_move_at = time.time()
            self._looks += 1
            self._prev_gray = None

    # -- detection ----------------------------------------------------------
    def _find_face(self, gray, scale):
        """Centre of the largest believable face, in FULL frame coordinates."""
        if self._cascade is None:
            return None
        min_px = int(config.TRACKER_MIN_FACE_PX * scale)
        faces = self._cascade.detectMultiScale(
            gray, scaleFactor=1.2, minNeighbors=5,
            minSize=(max(12, min_px), max(12, min_px)))
        if len(faces) == 0:
            return None
        # Largest, which indoors is a good enough proxy for nearest.
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        return ((x + w / 2.0) / scale, (y + h / 2.0) / scale)

    def _find_movement(self, gray, scale):
        """
        Centre of the largest moving blob, in FULL frame coordinates.

        Only meaningful while the head is still - see the note at the top of
        this file - so it refuses to answer otherwise.
        """
        prev = self._prev_gray
        if prev is None or prev.shape != gray.shape:
            return None
        if time.time() - self._last_move_at < MOTION_NEEDS_STILL_S:
            return None

        delta = cv2.absdiff(prev, gray)
        _, mask = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)
        mask = cv2.dilate(mask, None, iterations=2)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        biggest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(biggest) < MOTION_MIN_AREA_FRAC * gray.size:
            return None

        x, y, w, h = cv2.boundingRect(biggest)
        # Aim at the upper third of a moving body, which is roughly where a
        # face is. Looking at the centre of a child means looking at their
        # stomach, and it shows.
        return ((x + w / 2.0) / scale, (y + h / 3.0) / scale)

    # -- nobody there -------------------------------------------------------
    def _maybe_idle(self):
        now = time.time()
        if now - self._last_seen_at < config.TRACKER_LOST_S:
            return
        if now - self._last_idle_at < config.TRACKER_RECENTRE_S:
            return
        self._last_idle_at = now
        self._mode = 'idle'
        self.robot.express('think')
        self._last_move_at = now

    # =======================================================================
    # Reporting
    # =======================================================================
    def describe(self):
        if not self.enabled:
            return 'tracking off in config.py'
        if self.error and not self.running:
            return 'not tracking ({})'.format(self.error)
        if not self.running:
            return 'tracking not started'
        seen = time.time() - self._last_seen_at if self._last_seen_at else None
        if seen is None or seen > config.TRACKER_LOST_S:
            return 'tracking, nobody in view'
        return 'tracking on {} ({} looks)'.format(self._mode, self._looks)
