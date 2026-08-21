#!/usr/bin/env python3
# check_robot.py - prove the Reachy Mini works before a session depends on it.
#
#     python tools/check_robot.py
#     python tools/check_robot.py --host 192.168.1.42
#     python tools/check_robot.py --pack dragon        (also test real narration)
#     python tools/check_robot.py --camera             (also test the tracker)
#
# WHY THIS EXISTS
# Same reason as the Phase 1 bench test in the README: the robot is a new piece
# of plumbing, and the time to find out it does not work is not with a room
# full of children waiting. This walks the four things the game asks of it, in
# the order that isolates a failure.
#
#   1. Connect.       Is there a robot on the network at all?
#   2. Move.          Do the head and antennas respond?
#   3. Speak.         Does a WAV reach its speaker, and how long does the
#                     upload take? (This is the number that decides whether
#                     preloading is optional or essential.)
#   4. See.           Does the camera deliver frames, and can it find a face?
#
# None of this touches the micro:bits. You can run it with nothing else set up.
#
# It ignores config.USE_ROBOT deliberately - you run this to find out whether
# to turn that on.

import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, os.pardir, 'computer_app'))
sys.path.insert(0, APP)
os.chdir(APP)               # config's paths are relative to computer_app

import config                                          # noqa: E402
from robot import wav_seconds                           # noqa: E402


def head(text):
    print('\n' + text)
    print('-' * len(text))


def ok(text):
    print('  [ok]   {}'.format(text))


def bad(text):
    print('  [FAIL] {}'.format(text))


def info(text):
    print('         {}'.format(text))


# ===========================================================================
# Version check
#
# The SDK and the software on the robot have to be roughly the same age. When
# they are not, the SDK fails with a bare "Network connection attempt failed",
# which sends you hunting for a network problem that is not there. The robot
# answers plain HTTP whatever version it is running, so ask it first and say
# something useful.
# ===========================================================================
def fetch_json(url, timeout=6):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return None


def installed_sdk_version():
    try:
        from importlib.metadata import version
        return version('reachy_mini')
    except Exception:
        return None


def step_versions(host, port):
    """Returns False only when the mismatch is bad enough to stop for."""
    status = fetch_json('http://{}:{}/api/daemon/status'.format(host, port))
    if status is None:
        info('the robot did not answer plain HTTP on port {}'.format(port))
        info('so it is either off, or not at this address')
        return True                 # let the SDK produce the real error

    on_robot = status.get('version')
    in_venv = installed_sdk_version()
    ok('the robot is running {}'.format(on_robot or 'an unknown version'))
    info('this computer has SDK {}'.format(in_venv or 'unknown'))

    if status.get('state') and status['state'] != 'running':
        info('daemon state is "{}"'.format(status['state']))

    backend = status.get('backend_status') or {}
    if backend.get('ready') is False:
        info('note: the motor backend reports it is not ready yet')

    if not on_robot or not in_venv:
        return True

    if on_robot.split('.')[:2] == in_venv.split('.')[:2]:
        ok('versions match')
        return True

    # This one asks the internet what the latest release is, so it is much
    # slower than the robot's own status endpoint and needs a longer rope.
    available = fetch_json(
        'http://{}:{}/update/available'.format(host, port), timeout=20) or {}
    latest = (available.get('update', {})
                       .get('reachy_mini', {})
                       .get('available_version'))

    bad('version mismatch: robot {} vs SDK {}'.format(on_robot, in_venv))
    info('These have to match. Update the robot - it is step 3 of Pollen\'s')
    info('own setup guide - at:')
    info('    http://{}:{}/settings'.format(host, port))
    if latest:
        info('It is offering {}.'.format(latest))
    info('Keep it on mains power; it reboots partway through.')
    return False


# ===========================================================================
# 1. Connect
# ===========================================================================
def step_connect(args):
    head('1. Connecting')

    try:
        import robot as robot_module
    except Exception as exc:
        bad('could not import robot.py: {}'.format(exc))
        return None

    if robot_module.ReachyMini is None:
        bad('the reachy_mini SDK is not installed')
        info('pip install reachy-mini')
        info('detail: {}'.format(robot_module._SDK_ERROR))
        return None
    ok('reachy_mini SDK found')

    if args.host:
        config.ROBOT_HOST = args.host
        config.ROBOT_CONNECT_MODE = 'network'
    info('looking for a daemon at {}:{} (mode {})'.format(
        config.ROBOT_HOST, config.ROBOT_PORT, config.ROBOT_CONNECT_MODE))

    if not step_versions(config.ROBOT_HOST, config.ROBOT_PORT):
        return None

    started = time.time()
    bot = robot_module.Robot(enabled=True)
    if not bot.ready:
        bad(bot.error or 'unknown failure')
        info('Check the robot is powered up and on the same network.')
        info('If reachy-mini.local does not resolve, pass --host <ip>.')
        return None

    ok('connected in {:.1f}s'.format(time.time() - started))
    if bot.error:
        info('warning: {}'.format(bot.error))
    return bot


# ===========================================================================
# 2. Move
# ===========================================================================
def step_move(bot):
    head('2. Moving')

    for name in ('listen', 'pass', 'fail', 'neutral'):
        print('  {} ...'.format(name), end='', flush=True)
        bot.express(name)
        # express() is deliberately asynchronous so the game never waits for
        # it. Here we do want to watch each one finish.
        while bot._expression is not None and bot._expression.is_alive():
            time.sleep(0.05)
        print(' done')

    if bot.error:
        bad(bot.error)
        return False
    ok('head and antennas respond')
    info('If nothing moved, the daemon is up but the motors are not -')
    info('check the robot is not still folded in its sleep pose.')
    return True


# ===========================================================================
# 3. Speak
# ===========================================================================
def step_speak(bot, pack_id):
    head('3. Speaking')

    if not config.ROBOT_NARRATES:
        info('ROBOT_NARRATES is off in config.py, so the game would use the')
        info('computer speakers. Testing the robot speaker anyway.')

    paths = []
    if pack_id:
        voice_dir = os.path.join(config.VOICE_DIR, pack_id)
        if os.path.isdir(voice_dir):
            paths = sorted(os.path.join(voice_dir, n)
                           for n in os.listdir(voice_dir) if n.endswith('.wav'))
        if not paths:
            bad('no built narration in {}'.format(voice_dir))
            info('Run tools/build_voice.py --pack {} first.'.format(pack_id))
            return False

    if not paths:
        info('No --pack given, so nothing to play.')
        info('Re-run with --pack dragon once you have built the voices.')
        return True

    # The first play of a file uploads it. That gap is the whole reason
    # ROBOT_PRELOAD_VOICES exists, so measure it rather than assume it.
    sample = paths[0]
    seconds = wav_seconds(sample)

    started = time.time()
    sent = bot.preload([sample])
    upload = time.time() - started

    if sent:
        ok('uploaded {} in {:.2f}s'.format(os.path.basename(sample), upload))
        if upload > 0.5:
            info('That is long enough to be noticeable mid-session.')
            info('Keep ROBOT_PRELOAD_VOICES = True.')
    else:
        info('no upload needed (running on the robot, or upload unsupported)')

    print('  playing {} ({:.1f}s) - listen to the robot ...'.format(
        os.path.basename(sample), seconds or 0))
    if not bot.speak(sample, wait=True):
        bad('speak() refused the file')
        return False
    ok('played without error')

    info('')
    info('NOW THE QUESTION THAT MATTERS: was it loud enough for the room?')
    info('The robot speaker sits a metre from the children rather than across')
    info('the hall. If it was not, set ROBOT_NARRATES = False and keep the PA.')
    info('If it was, re-tune LOUD_THRESHOLD in microbit/mb_player.py against')
    info('it - see the Tuning section of the README.')
    return True


# ===========================================================================
# 4. See
# ===========================================================================
def step_camera(bot):
    head('4. Seeing')

    size = bot.camera_size()
    if size:
        ok('camera reports {} x {}'.format(size[0], size[1]))

    frame = None
    for _ in range(20):
        frame = bot.grab_frame()
        if frame is not None:
            break
        time.sleep(0.25)

    if frame is None:
        bad('no camera frames after 5s')
        info('The daemon may have media released, or another app holds it.')
        return False
    ok('got a frame, shape {}'.format(getattr(frame, 'shape', '?')))

    try:
        import tracker as tracker_module
    except Exception as exc:
        bad('could not import tracker.py: {}'.format(exc))
        return False

    if tracker_module.cv2 is None:
        bad('opencv is not installed, so there is no detector')
        info('pip install opencv-python')
        return False
    ok('opencv found')

    trk = tracker_module.Tracker(bot, enabled=True)
    if trk.error:
        info('note: {}'.format(trk.error))

    print('')
    print('  Stand in front of the robot. Ten seconds of live tracking.')
    print('  It should turn towards you and hold you near the centre.')
    print('')
    trk.start()
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(1.0)
        print('  {}'.format(trk.describe()))
    trk.stop()

    if trk._looks == 0:
        bad('it never moved to look at anything')
        info('Try more light on your face, or stand further back so your')
        info('whole head is in frame.')
        return False
    ok('tracked, {} head moves'.format(trk._looks))
    return True


# ===========================================================================
def main():
    parser = argparse.ArgumentParser(
        description='Bench test a Reachy Mini before using it in a session.')
    parser.add_argument('--host', help='robot IP or hostname, overrides config')
    parser.add_argument('--pack', help='also play a real narration line')
    parser.add_argument('--camera', action='store_true',
                        help='also test the camera and live tracking')
    args = parser.parse_args()

    print('=' * 68)
    print(' Reachy Mini bench test')
    print('=' * 68)

    bot = step_connect(args)
    if bot is None:
        print('\nStopped at step 1. Nothing else can be tested until the SDK')
        print('can connect, so deal with the above first.')
        return 1

    results = [step_move(bot), step_speak(bot, args.pack)]
    if args.camera:
        results.append(step_camera(bot))
    else:
        head('4. Seeing')
        info('skipped, pass --camera to test it')

    head('Result')
    if all(results):
        ok('everything passed')
        print('\n  Turn USE_ROBOT = True in computer_app/config.py'
              '{}.'.format(', and USE_TRACKER = True' if args.camera else ''))
    else:
        bad('something above failed - the game still runs without the robot')
        print('\n  Leave USE_ROBOT = False and the session is unaffected.')

    bot.close()
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
