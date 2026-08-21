#!/usr/bin/env python3
# simulate_robot.py - run the REAL robot code with no robot.
#
#     python tools/simulate_robot.py
#
# Why this exists: Reachy Mini has a long lead time and lives on a network, so
# the narration routing, the upload cache and the tracker's aiming rules would
# otherwise go untested until the day they matter. This stubs the reachy_mini
# SDK and OpenCV, then drives the actual computer_app/robot.py and
# computer_app/tracker.py so their bookkeeping can be checked in a second.
#
# Like simulate_wand.py, it proves nothing physical. It cannot tell you whether
# the robot is loud enough for the room, whether a face detector copes with
# your lighting, or whether the head turns far enough to see a child at the
# edge of the group. Those need the robot, and tools/check_robot.py.
#
# What it does prove:
#   - narration reaches the robot, and falls back cleanly when it cannot
#   - each WAV is uploaded once and thereafter played by name
#   - say() blocks for the length of the line, which is what holds the pacing
#     together now that nothing reports when playback finishes
#   - microphone challenges freeze the head, and unfreeze it afterwards
#   - the tracker aims where it should, and stays still when it should

import os
import sys
import types
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, os.pardir, 'computer_app'))

import numpy as np

FAILURES = []


def check(label, condition, detail=''):
    if condition:
        print('  PASS  {}'.format(label))
    else:
        FAILURES.append(label)
        print('  FAIL  {}{}'.format(label, '  <- ' + detail if detail else ''))


def section(title):
    print('\n' + title)


# ===========================================================================
# A fake Reachy Mini
#
# Only the handful of calls robot.py actually makes. goto_target returns
# instantly rather than taking its duration, so the suite runs in a second.
# ===========================================================================
class FakeAudioBackend(object):
    def __init__(self):
        self.uploaded = []

    def upload_sound(self, path):
        self.uploaded.append(path)


class FakeCamera(object):
    resolution = (640, 480)


class FakeMedia(object):
    def __init__(self):
        self.audio = FakeAudioBackend()
        self.camera = FakeCamera()
        self.played = []
        self.stops = 0
        self.frame = None

    def play_sound(self, name):
        self.played.append(name)

    def stop_playing(self):
        self.stops += 1

    def get_frame(self):
        return self.frame


class FakeMini(object):
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.media = FakeMedia()
        self.woke = False
        self.wobbling = False
        self.slept = False
        self.moves = []
        self.looks = []

    def wake_up(self):
        self.woke = True

    def enable_wobbling(self):
        self.wobbling = True

    def goto_target(self, head=None, antennas=None, duration=0.5, method=None):
        self.moves.append({'head': head, 'antennas': antennas,
                           'duration': duration, 'method': method})

    def look_at_image(self, u, v, duration=1.0):
        self.looks.append((u, v, duration))

    def goto_sleep(self):
        self.slept = True

    def __exit__(self, *args):
        pass


def fake_create_head_pose(**kwargs):
    return dict(kwargs)


# ===========================================================================
# A fake OpenCV
#
# Enough of the API for tracker.py to run. The detector is scripted: whatever
# is put in FakeCascade.faces is what it "sees", so the tests exercise the
# tracker's decisions rather than anybody's computer vision.
# ===========================================================================
class FakeCascade(object):
    faces = []

    def __init__(self, path=None):
        pass

    def empty(self):
        return False

    def detectMultiScale(self, gray, **kwargs):
        return list(FakeCascade.faces)


def _fake_findContours(mask, mode, method):
    """One contour: the bounding box of everything non-zero."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return [], None
    box = (int(xs.min()), int(ys.min()),
           int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
    return [box], None


def build_fake_cv2():
    cv2 = types.ModuleType('cv2')
    cv2.data = types.SimpleNamespace(haarcascades='')
    cv2.CascadeClassifier = FakeCascade
    cv2.COLOR_BGR2GRAY = 0
    cv2.RETR_EXTERNAL = 0
    cv2.CHAIN_APPROX_SIMPLE = 0
    cv2.THRESH_BINARY = 0

    cv2.resize = lambda img, size, fx=1.0, fy=1.0: img[
        ::max(1, int(round(1 / fy))), ::max(1, int(round(1 / fx)))]
    cv2.cvtColor = lambda img, code: (
        img[:, :, 0] if img.ndim == 3 else img).astype(np.uint8)
    cv2.equalizeHist = lambda gray: gray
    cv2.absdiff = lambda a, b: np.abs(
        a.astype(np.int16) - b.astype(np.int16)).astype(np.uint8)
    cv2.threshold = lambda src, thresh, maxval, kind: (
        thresh, ((src > thresh) * maxval).astype(np.uint8))
    cv2.dilate = lambda src, kernel, iterations=1: src
    cv2.findContours = _fake_findContours
    cv2.contourArea = lambda box: float(box[2] * box[3])
    cv2.boundingRect = lambda box: box
    return cv2


def install_stubs():
    sdk = types.ModuleType('reachy_mini')
    sdk.ReachyMini = FakeMini
    utils = types.ModuleType('reachy_mini.utils')
    utils.create_head_pose = fake_create_head_pose
    sdk.utils = utils

    sys.modules['reachy_mini'] = sdk
    sys.modules['reachy_mini.utils'] = utils
    sys.modules['cv2'] = build_fake_cv2()

    sys.path.insert(0, APP)
    os.chdir(APP)


# ===========================================================================
# A real, tiny WAV, so durations are read rather than invented
# ===========================================================================
def write_wav(path, seconds, rate=8000):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with wave.open(path, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b'\x00\x00' * int(rate * seconds))
    return path


# ===========================================================================
# Tests
# ===========================================================================
def fresh_robot(config, robot_module, **flags):
    config.USE_ROBOT = True
    config.ROBOT_NARRATES = True
    config.ROBOT_WOBBLE = True
    config.ROBOT_EMOTES = True
    config.ROBOT_PRELOAD_VOICES = True
    config.ROBOT_SPEAK_PAD_S = 0.0
    for key, value in flags.items():
        setattr(config, key, value)
    bot = robot_module.Robot(enabled=True)
    settle(bot)
    return bot


def settle(bot):
    """Wait for any expression thread to finish."""
    thread = bot._expression
    if thread is not None:
        thread.join(timeout=2.0)


def test_connect(config, robot_module):
    section('connecting')
    bot = fresh_robot(config, robot_module)
    check('reports ready', bot.ready)
    check('woke the robot up', bot.mini.woke)
    check('enabled audio-reactive wobbling', bot.mini.wobbling)
    check('used the configured host',
          bot.mini.kwargs.get('host') == config.ROBOT_HOST)

    off = robot_module.Robot(enabled=False)
    check('a disabled robot is not ready', not off.ready)
    check('and says so plainly', 'off' in off.describe())
    check('its methods are safe to call',
          off.speak('nope.wav') is False and off.express('pass') is None)


def test_upload_once(config, robot_module, tmp):
    section('narration reaches the robot')
    bot = fresh_robot(config, robot_module)
    line = write_wav(os.path.join(tmp, 'intro.wav'), 0.05)

    check('speak() accepts a real file', bot.speak(line, wait=False))
    check('the file was uploaded', bot.mini.media.audio.uploaded == [line])
    check('and played by bare name', bot.mini.media.played == ['intro.wav'])

    bot.speak(line, wait=False)
    check('a second airing does not re-upload',
          len(bot.mini.media.audio.uploaded) == 1,
          'uploaded {}'.format(bot.mini.media.audio.uploaded))
    check('but does play again', bot.mini.media.played.count('intro.wav') == 2)

    check('a missing file is refused', bot.speak(os.path.join(tmp, 'nope.wav'))
          is False)
    check('so the caller can fall back',
          len(bot.mini.media.played) == 2)

    bot = fresh_robot(config, robot_module, ROBOT_NARRATES=False)
    check('narration off means the robot declines', bot.speak(line) is False)


def test_speak_blocks(config, robot_module, tmp):
    section('speak() holds for the length of the line')
    import time
    bot = fresh_robot(config, robot_module)

    long_line = write_wav(os.path.join(tmp, 'long.wav'), 0.40)
    started = time.time()
    bot.speak(long_line, wait=True)
    waited = time.time() - started
    check('waited about the WAV duration', 0.35 <= waited <= 0.75,
          'waited {:.2f}s for a 0.40s file'.format(waited))

    started = time.time()
    bot.speak(long_line, wait=False)
    check('wait=False returns immediately', time.time() - started < 0.1)

    check('duration is read from the header',
          abs(robot_module.wav_seconds(long_line) - 0.40) < 0.02)
    check('an unreadable file has no duration',
          robot_module.wav_seconds(os.path.join(tmp, 'nope.wav')) is None)


def test_hold_still(config, robot_module):
    section('holding still for microphone challenges')
    bot = fresh_robot(config, robot_module)

    bot.express('listen')
    settle(bot)
    check('expressions move the head', len(bot.mini.moves) > 0)

    before = len(bot.mini.moves)
    bot.hold_still()
    check('reports being held still', bot.is_held_still())
    check('silenced playback', bot.mini.media.stops > 0)

    bot.express('pass')
    settle(bot)
    check('expressions are suppressed', len(bot.mini.moves) == before)
    check('and so is tracking', bot.look_at_pixel(100, 100) is False)
    check('nothing was sent to the head',
          len(bot.mini.looks) == 0)

    bot.release()
    check('released', not bot.is_held_still())
    check('tracking works again', bot.look_at_pixel(100, 100) is True)


def test_audio_routing(config, robot_module, tmp):
    section('audio.py prefers the robot')
    import audio as audio_module

    config.VOICE_DIR = tmp
    config.AUDIO_ENABLED = True
    bot = fresh_robot(config, robot_module)

    pack_dir = os.path.join(tmp, 'dragon')
    write_wav(os.path.join(pack_dir, 'intro.wav'), 0.05)
    write_wav(os.path.join(pack_dir, 'gate.wav'), 0.05)

    sound = audio_module.Audio('dragon', enabled=True, robot=bot)
    check('describes itself as robot narration', 'robot' in sound.describe())

    sent = sound.preload(['intro', 'gate', 'missing'])
    check('preloads only the lines that exist', sent == 2,
          'preloaded {}'.format(sent))

    sound.say('intro', 'the dragon stirs', wait=False)
    check('spoke through the robot', 'intro.wav' in bot.mini.media.played)

    # A line with no WAV must not vanish silently: it falls through to the
    # printed fallback, which is what lets a session run before voices exist.
    before = len(bot.mini.media.played)
    sound.say('missing', 'this line was never built', wait=False)
    check('an unbuilt line does not reach the robot',
          len(bot.mini.media.played) == before)

    sound.stop()
    check('stop() silences the robot too', bot.mini.media.stops > 0)


def test_engine_hooks(config, robot_module):
    section('the engine drives the robot')
    import protocol as P
    from engine import Engine
    from transports.base import Transport

    class DeafTransport(Transport):
        def __init__(self):
            self.sent = []

        def start(self, on_message):
            pass

        def send_command(self, line):
            self.sent.append(line)
            return True

        def stop(self):
            pass

        def status(self):
            return {'connected': True, 'target': 'fake', 'error': None}

    class SilentAudio(object):
        def __init__(self):
            self.quiet_calls = 0

        def say(self, *a, **kw):
            pass

        def sfx(self, *a, **kw):
            pass

        def stop(self):
            pass

        def go_quiet(self, lead=None):
            self.quiet_calls += 1

        def describe(self):
            return 'silent'

        def missing_lines(self, ids):
            return []

        def preload(self, ids):
            return 0

    config.ACTIVE_PLAYERS = 2
    config.ANSWER_GRACE_S = 0.0
    bot = fresh_robot(config, robot_module)
    quiet = SilentAudio()

    engine = Engine(DeafTransport(), lambda pack_id: quiet, robot=bot)
    check('the robot appears in the snapshot',
          'robot' in engine.snapshot() and engine.snapshot()['robot'])

    # A microphone challenge must freeze the head: the wands hear servos as
    # readily as they hear a clap.
    step = {'id': 'shout', 'type': 'challenge', 'verb': 'CLAP', 'arg': 1,
            'win': 1000, 'require': 'any'}
    engine._run_challenge(step)

    check('narration went quiet for the microphone', quiet.quiet_calls == 1)
    check('the head was released afterwards', not bot.is_held_still())

    settle(bot)
    check('a verdict expression was played', len(bot.mini.moves) > 0)

    # A non-microphone challenge must not go quiet at all.
    quiet.quiet_calls = 0
    engine._run_challenge({'id': 'press', 'type': 'challenge', 'verb': 'BTNA',
                           'arg': 1, 'win': 1000, 'require': 'any'})
    check('a button challenge does not silence anything',
          quiet.quiet_calls == 0)
    check('and does not leave the head held', not bot.is_held_still())
    check('IDLE is still the verb vocabulary we expect', 'CLAP' in P.MIC_VERBS)


def test_tracker(config, robot_module):
    section('the tracker aims the head')
    import tracker as tracker_module

    config.TRACKER_DEADZONE_PX = 60
    config.TRACKER_SETTLE_S = 0.35
    config.TRACKER_MIN_FACE_PX = 48

    bot = fresh_robot(config, robot_module)
    trk = tracker_module.Tracker(bot, enabled=True)
    check('the tracker started up', trk.error is None,
          'error: {}'.format(trk.error))

    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # NOTE: detection runs on a half-size copy of the frame, so scripted faces
    # are given in those coordinates. A box at (200, 50) here is a child at
    # (400, 100) in the real image, and the tracker is expected to hand the
    # full-size figure to the robot.
    import time

    # A face off to the right must pull the head that way.
    FakeCascade.faces = [(200, 50, 60, 60)]
    trk._last_move_at = 0
    trk._consider(frame)
    check('looked at the face', len(bot.mini.looks) == 1)
    if bot.mini.looks:
        u, v, _ = bot.mini.looks[-1]
        check('scaled back up to full-frame coordinates', 400 < u < 520,
              'aimed at u={}, expected about 460'.format(u))
        check('aimed above centre', v < 240, 'aimed at v={}'.format(v))

    # A face already centred is left alone, or the head twitches forever.
    bot.mini.looks = []
    trk._last_move_at = 0
    FakeCascade.faces = [(145, 105, 30, 30)]
    trk._consider(frame)
    check('a centred face is not chased', len(bot.mini.looks) == 0,
          'looks: {}'.format(bot.mini.looks))

    # Straight after a move the view is still sliding, so frames lie and must
    # be ignored however interesting they look.
    bot.mini.looks = []
    FakeCascade.faces = [(200, 50, 60, 60)]
    trk._last_move_at = time.time()
    trk._consider(frame)
    check('frames during a head move are ignored', len(bot.mini.looks) == 0,
          'looks: {}'.format(bot.mini.looks))

    # Nothing visible: fall through to movement, but only once the head has
    # been still, because a moving camera makes every pixel look like motion.
    bot.mini.looks = []
    trk._last_move_at = 0
    trk._prev_gray = None
    FakeCascade.faces = []
    grey = np.full((480, 640, 3), 10, dtype=np.uint8)
    trk._consider(grey)
    moved = grey.copy()
    moved[100:200, 380:480] = 200
    trk._consider(moved)
    check('movement is tracked when no face is visible',
          len(bot.mini.looks) == 1, 'looks: {}'.format(bot.mini.looks))
    check('and it is reported as motion', trk._mode == 'motion')

    # An empty view eventually produces an idle glance rather than nothing.
    bot.mini.moves = []
    trk._last_seen_at = 0
    trk._last_idle_at = 0
    trk._maybe_idle()
    settle(bot)
    check('an empty room gets an idle look-around', len(bot.mini.moves) > 0)

    check('describes itself sensibly', 'track' in trk.describe())


# ===========================================================================
def main():
    import shutil
    import tempfile

    install_stubs()

    import config
    import robot as robot_module

    tmp = tempfile.mkdtemp(prefix='quest-robot-')

    print('Simulating computer_app/robot.py and tracker.py')
    print('(logic only - volume, lighting and reach still need the robot)')

    try:
        test_connect(config, robot_module)
        test_upload_once(config, robot_module, tmp)
        test_speak_blocks(config, robot_module, tmp)
        test_hold_still(config, robot_module)
        test_audio_routing(config, robot_module, tmp)
        test_engine_hooks(config, robot_module)
        test_tracker(config, robot_module)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print('')
    if FAILURES:
        print('{} check(s) FAILED:'.format(len(FAILURES)))
        for label in FAILURES:
            print('  - {}'.format(label))
        return 1
    print('All checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
