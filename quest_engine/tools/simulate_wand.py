#!/usr/bin/env python3
# simulate_wand.py - run the REAL wand firmware on a computer.
#
#     python tools/simulate_wand.py
#
# Why this exists: the detectors and the challenge state machine in
# microbit/mb_player.py are the fiddly part of this game, and debugging them
# with five children in a room is miserable. This stubs out the micro:bit API,
# executes mb_player.py up to its main loop, and then drives tick() by hand so
# the logic can be checked in a second.
#
# It does NOT and cannot verify anything physical: whether the microphone
# threshold suits your PA, whether 'left' means what a child thinks it means,
# or whether the radio reaches across the hall. Those need the real thing.
# What it does verify is that the bookkeeping is right - counting, timing out,
# flushing stale gestures, the acknowledge handshake, and the compass guard.
#
# It imports the firmware by executing the source, so it always tests the file
# you are about to flash rather than a copy that can drift out of date.

import os
import random
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(HERE, os.pardir, 'microbit', 'mb_player.py')


# ===========================================================================
# Fake micro:bit hardware
# ===========================================================================
class Clock(object):
    def __init__(self):
        self.t = 0

    def advance(self, ms):
        self.t += ms


class FakeImage(object):
    YES = NO = ARROW_W = ARROW_E = ARROW_S = None

    def __init__(self, spec=''):
        self.spec = spec

    def __repr__(self):
        return 'Image({!r})'.format(self.spec)


class FakeDisplay(object):
    def __init__(self):
        self.last = None
        self.shown = []

    def show(self, image, *args, **kwargs):
        self.last = image
        self.shown.append(image)

    def scroll(self, *args, **kwargs):
        pass

    def clear(self):
        self.last = None


class FakeButton(object):
    def __init__(self):
        self._presses = 0
        self.down = False

    def press(self, times=1):
        self._presses += times

    def get_presses(self):
        n, self._presses = self._presses, 0
        return n

    def was_pressed(self):
        n, self._presses = self._presses, 0
        return n > 0

    def is_pressed(self):
        return self.down


class FakeAccelerometer(object):
    def __init__(self):
        self.x = 0
        self.y = 0
        self.z = -1000
        self._gestures = []

    def get_x(self):
        return self.x

    def get_y(self):
        return self.y

    def get_z(self):
        return self.z

    def queue(self, *names):
        self._gestures.extend(names)

    def get_gestures(self):
        out = tuple(self._gestures)
        self._gestures = []
        return out

    def was_gesture(self, name):
        hit = name in self._gestures
        self._gestures = []
        return hit


class FakeSoundEvent(object):
    LOUD = 'loud'
    QUIET = 'quiet'


class FakeMicrophone(object):
    def __init__(self):
        self.level = 0
        self.threshold = None
        self._events = []

    def set_threshold(self, event, value):
        self.threshold = value

    def sound_level(self):
        return self.level

    def fire(self, event=FakeSoundEvent.LOUD):
        self._events.append(event)

    def was_event(self, event):
        hit = event in self._events
        self._events = []
        return hit

    def get_events(self):
        out = tuple(self._events)
        self._events = []
        return out


class FakeLogo(object):
    CAPACITIVE = 'capacitive'
    RESISTIVE = 'resistive'

    def __init__(self):
        self.touched = False
        self.mode = None

    def is_touched(self):
        return self.touched

    def set_touch_mode(self, mode):
        self.mode = mode


class FakeCompass(object):
    def __init__(self):
        self.calibrated = False
        self.bearing = 0

    def is_calibrated(self):
        return self.calibrated

    def calibrate(self):
        self.calibrated = True

    def heading(self):
        return self.bearing


class FakeRadio(object):
    def __init__(self):
        self.sent = []
        self.inbox = []

    def config(self, **kwargs):
        pass

    def on(self):
        pass

    def off(self):
        pass

    def send(self, message):
        self.sent.append(message)

    def receive_full(self):
        if self.inbox:
            return self.inbox.pop(0)
        return None

    def deliver(self, text, rssi=-60):
        # Real radio.receive_full() hands back bytes with a 3-byte header that
        # the firmware strips, so the fake has to include one too.
        self.inbox.append((b'\x00\x00\x00' + text.encode('utf-8'), rssi, 0))


# ===========================================================================
# Loading the firmware
# ===========================================================================
class Wand(object):
    """The firmware's module namespace plus handles on the fake hardware."""

    def __init__(self):
        self.clock = Clock()
        self.display = FakeDisplay()
        self.button_a = FakeButton()
        self.button_b = FakeButton()
        self.accelerometer = FakeAccelerometer()
        self.microphone = FakeMicrophone()
        self.pin_logo = FakeLogo()
        self.compass = FakeCompass()
        self.radio = FakeRadio()

        microbit = types.ModuleType('microbit')
        microbit.display = self.display
        microbit.button_a = self.button_a
        microbit.button_b = self.button_b
        microbit.accelerometer = self.accelerometer
        microbit.microphone = self.microphone
        microbit.pin_logo = self.pin_logo
        microbit.compass = self.compass
        microbit.SoundEvent = FakeSoundEvent
        microbit.Image = FakeImage
        microbit.running_time = lambda: self.clock.t
        microbit.sleep = lambda ms: self.clock.advance(ms)
        microbit.panic = lambda *a: None
        microbit.reset = lambda *a: None

        music = types.ModuleType('music')
        music.play = lambda *a, **k: None
        music.pitch = lambda *a, **k: None

        sys.modules['microbit'] = microbit
        sys.modules['radio'] = self.radio
        sys.modules['music'] = music

        with open(FIRMWARE, encoding='utf-8') as handle:
            source = handle.read()

        marker = '\nwhile True:'
        if marker not in source:
            raise RuntimeError(
                'could not find the main loop in mb_player.py - if you renamed '
                'or restructured it, update the marker in this file'
            )
        head = source.split(marker)[0]

        self.ns = {'__name__': 'mb_player'}
        exec(compile(head, 'mb_player.py', 'exec'), self.ns)

    # -- driving -----------------------------------------------------------
    def tick(self, dt=10):
        self.clock.advance(dt)
        self.ns['tick'](self.clock.t)

    def deliver(self, text, rssi=-60):
        self.radio.deliver(text, rssi)

    def command(self, seq, verb, arg=0, win=6000, mask=31, ack=0):
        self.deliver('C|{}|{}|{}|{}|{}|{}'.format(seq, verb, arg, win, mask, ack))

    @property
    def state(self):
        return self.ns['state']

    @property
    def result(self):
        return self.ns['result']

    def answers(self):
        return [m for m in self.radio.sent if m.startswith('A|')]

    def last_answer(self):
        found = self.answers()
        return found[-1] if found else None

    def settle(self, ms, step=10):
        """Run the loop forward, as the real firmware would at 10 ms a pass."""
        for _ in range(max(1, ms // step)):
            self.tick(step)


# ===========================================================================
# Checks
# ===========================================================================
FAILURES = []


def check(label, condition, detail=''):
    if condition:
        print('  PASS  {}'.format(label))
    else:
        FAILURES.append(label)
        print('  FAIL  {}{}'.format(label, '  <- ' + detail if detail else ''))


def boot():
    """Fresh wand, past the boot sequence, mute window expired."""
    wand = Wand()
    wand.settle(600)
    return wand


def test_boot():
    print('\nboot')
    wand = boot()
    check('player id defaults to 1', wand.ns['PLAYER_ID'] == 1,
          'got {}'.format(wand.ns['PLAYER_ID']))
    check('starts idle', wand.state == 'IDLE', wand.state)
    check('heartbeats are emitted',
          any(m.startswith('H|1|') for m in wand.radio.sent))


def test_resting_when_not_addressed():
    print('\naddressing one child leaves the others resting')
    wand = boot()
    wand.command(1, 'BTNA', 3, 6000, mask=0b00010)   # player 2 only
    wand.tick()
    check('not addressed -> RESTING', wand.state == 'RESTING', wand.state)
    check('sends no answer', wand.last_answer() is None)

    wand.command(2, 'BTNA', 1, 6000, mask=0b00001)   # player 1
    wand.tick()
    check('addressed -> ARMED', wand.state == 'ARMED', wand.state)


def test_button_counting():
    print('\ncounting button presses')
    wand = boot()
    wand.command(3, 'BTNA', 3, 6000)
    wand.tick()
    check('armed', wand.state == 'ARMED', wand.state)

    wand.button_a.press(2)
    wand.tick()
    check('two of three is not finished', wand.state == 'ARMED', wand.state)

    wand.button_a.press(1)
    wand.tick()
    check('third press completes it', wand.state == 'DONE', wand.state)
    check('result is OK', wand.result == 'OK', wand.result)

    answer = wand.last_answer()
    parts = (answer or '').split('|')
    check('answer is well formed', answer is not None and len(parts) == 6, answer)
    check('answer carries our id and the seq',
          parts[1] == '1' and parts[2] == '3', answer)
    check('reaction time is plausible', 0 < int(parts[4]) < 1000, answer)


def test_window_expiry():
    print('\nmissing the window')
    wand = boot()
    wand.command(4, 'SHAKE', 2, 1000)
    wand.tick()
    wand.settle(900)
    check('still armed inside the window', wand.state == 'ARMED', wand.state)
    wand.settle(300)
    check('expires to DONE', wand.state == 'DONE', wand.state)
    check('result is FAIL', wand.result == 'FAIL', wand.result)


def test_stale_gesture_is_flushed():
    print('\nstale gesture from the previous challenge is discarded')
    wand = boot()
    wand.accelerometer.queue('shake')            # left over from earlier
    wand.command(5, 'SHAKE', 1, 5000)
    wand.tick()
    check('leftover shake did not complete it', wand.state == 'ARMED',
          'state {} - arm() is not flushing get_gestures()'.format(wand.state))

    wand.accelerometer.queue('shake')            # a real one
    wand.tick()
    check('a fresh shake completes it', wand.state == 'DONE', wand.state)


def test_wrong_gesture_ignored():
    print('\nwrong gesture does not count')
    wand = boot()
    wand.command(6, 'TILTL', 1, 5000)
    wand.tick()
    wand.accelerometer.queue('right', 'shake', 'face up')
    wand.tick()
    check('other gestures are ignored', wand.state == 'ARMED', wand.state)
    wand.accelerometer.queue('left')
    wand.tick()
    check('the asked-for gesture counts', wand.state == 'DONE', wand.state)


def test_clap_debounce():
    print('\nclap debounce')
    wand = boot()
    wand.command(7, 'CLAP', 2, 8000)
    wand.tick()
    wand.settle(500)                             # clear the self-chirp mute

    wand.microphone.fire()
    wand.tick()
    check('first clap counts', wand.ns['count'] == 1, wand.ns['count'])

    wand.microphone.fire()                       # an echo, 10 ms later
    wand.tick()
    check('echo inside the debounce is ignored', wand.ns['count'] == 1,
          'count {} - CLAP_DEBOUNCE_MS is not holding'.format(wand.ns['count']))

    wand.settle(300)
    wand.microphone.fire()
    wand.tick()
    check('a separate clap counts', wand.state == 'DONE', wand.state)


def test_own_chirp_not_heard_as_clap():
    print('\nthe wand does not hear its own chirp as a clap')
    wand = boot()
    wand.command(8, 'BTNA', 1, 5000)
    wand.tick()
    wand.button_a.press()
    wand.tick()                                  # answers OK, chirps, mutes mic

    wand.command(9, 'CLAP', 1, 5000)
    wand.tick()
    wand.microphone.fire()                       # the tail of our own chirp
    wand.tick()
    check('clap during the mute window is ignored', wand.state == 'ARMED',
          'state {} - MIC_MUTE_MS is not holding'.format(wand.state))

    wand.settle(500)
    wand.microphone.fire()
    wand.tick()
    check('clap after the mute window counts', wand.state == 'DONE', wand.state)


def test_hold_resets_on_release():
    print('\nhold restarts if they let go')
    wand = boot()
    wand.command(10, 'HOLD', 1000, 10000)
    wand.tick()

    wand.pin_logo.touched = True
    wand.settle(700)
    check('700 ms of a 1000 ms hold is not enough', wand.state == 'ARMED',
          wand.state)

    wand.pin_logo.touched = False
    wand.tick()
    wand.pin_logo.touched = True
    wand.settle(700)
    check('the timer restarted after the release', wand.state == 'ARMED',
          'state {} - _sustain() is not resetting run_start'.format(wand.state))

    wand.settle(400)
    check('a full hold completes it', wand.state == 'DONE', wand.state)
    check('result is OK', wand.result == 'OK', wand.result)


def test_level():
    print('\nholding it level')
    wand = boot()
    wand.command(11, 'LEVEL', 500, 10000)
    wand.tick()
    wand.accelerometer.x = 900                   # tipped over
    wand.settle(600)
    check('tipped over does not pass', wand.state == 'ARMED', wand.state)
    wand.accelerometer.x = 20                    # flat
    wand.settle(700)
    check('flat for long enough passes', wand.state == 'DONE', wand.state)


def test_compass_guard():
    print('\ncompass guard')
    wand = boot()
    check('compass starts uncalibrated', not wand.compass.calibrated)
    wand.command(12, 'POINT', 45, 15000)
    wand.tick()
    check('uncalibrated POINT answers immediately', wand.state == 'DONE',
          wand.state)
    check('and says NOCAL rather than FAIL', wand.result == 'NOCAL',
          wand.result)
    check('NOCAL reaches the bridge',
          'NOCAL' in (wand.last_answer() or ''), wand.last_answer())


def test_point_when_calibrated():
    print('\npointing to a bearing')
    wand = boot()
    wand.compass.calibrated = True
    wand.compass.bearing = 200
    wand.command(13, 'POINT', 45, 15000)
    wand.tick()
    check('armed once calibrated', wand.state == 'ARMED', wand.state)

    wand.settle(1500)
    check('facing the wrong way does not pass', wand.state == 'ARMED',
          wand.state)

    wand.compass.bearing = 355                   # 50 degrees off, wraps past 0
    wand.settle(1200)
    check('outside tolerance across the 0/360 seam does not pass',
          wand.state == 'ARMED',
          'state {} - point_error() wraparound is wrong'.format(wand.state))

    wand.compass.bearing = 35                    # 10 degrees off: inside 25
    wand.settle(1300)
    check('inside tolerance passes', wand.state == 'DONE', wand.state)


def test_acknowledge_stops_resends():
    print('\nacknowledgement stops the resends')
    wand = boot()
    wand.command(14, 'BTNA', 1, 6000)
    wand.tick()
    wand.button_a.press()
    wand.tick()
    check('answered', wand.state == 'DONE', wand.state)

    wand.settle(1500)
    unacked = len(wand.answers())
    check('keeps resending while unacknowledged', unacked > 1,
          'only {} sends'.format(unacked))

    # The bridge now repeats the command with our bit set in <ack>.
    wand.command(14, 'BTNA', 1, 6000, ack=0b00001)
    wand.tick()
    wand.settle(2000)
    check('stops once acknowledged', len(wand.answers()) == unacked,
          '{} -> {} sends after the ack'.format(unacked, len(wand.answers())))


def test_resend_is_capped():
    print('\nresends are capped even with no acknowledgement')
    wand = boot()
    wand.command(15, 'BTNA', 1, 6000)
    wand.tick()
    wand.button_a.press()
    wand.tick()
    wand.settle(8000)
    sends = len(wand.answers())
    check('capped at MAX_ANSWER_SENDS',
          sends <= wand.ns['MAX_ANSWER_SENDS'],
          '{} sends, cap is {}'.format(sends, wand.ns['MAX_ANSWER_SENDS']))


def test_idle_command():
    print('\nstanding down')
    wand = boot()
    wand.command(16, 'BTNA', 3, 6000)
    wand.tick()
    check('armed', wand.state == 'ARMED', wand.state)
    wand.command(17, 'IDLE', 0, 0)
    wand.tick()
    check('IDLE returns to idle', wand.state == 'IDLE', wand.state)


def test_repeat_is_ignored():
    print('\nrepeated commands do not re-arm')
    wand = boot()
    wand.command(18, 'BTNA', 2, 6000)
    wand.tick()
    wand.button_a.press()
    wand.tick()
    check('one of two counted', wand.ns['count'] == 1, wand.ns['count'])

    wand.command(18, 'BTNA', 2, 6000)            # the bridge's 250 ms repeat
    wand.tick()
    check('progress survives the repeat', wand.ns['count'] == 1,
          'count {} - a repeat re-armed and wiped progress'.format(
              wand.ns['count']))


def test_corrupt_packets():
    print('\nmalformed radio traffic')
    wand = boot()
    for junk in ('C|nope|BTNA|3|6000|31|0', 'C|1|BTNA', 'garbage',
                 'C||||||', 'A|1|2|OK|5|6', 'B|P1', ''):
        wand.deliver(junk)
        wand.tick()
    check('survives junk without crashing', wand.state == 'IDLE', wand.state)

    wand.command(19, 'BTNA', 1, 6000)
    wand.tick()
    wand.button_a.press()
    wand.tick()
    check('still works afterwards', wand.state == 'DONE', wand.state)


def test_beacon_proximity():
    print('\nbeacon proximity for NEAR')
    wand = boot()
    wand.command(20, 'NEAR', 0, 60000)
    wand.tick()
    for _ in range(20):
        wand.deliver('B|P1', rssi=-85)           # far away
        wand.tick()
    check('a distant beacon does not pass', wand.state == 'ARMED', wand.state)

    for _ in range(20):
        wand.deliver('B|P1', rssi=-40)           # right next to it
        wand.tick()
    check('a close beacon passes', wand.state == 'DONE', wand.state)


def test_beacon_goes_stale():
    print('\nstale beacon readings are forgotten')
    wand = boot()
    for _ in range(20):
        wand.deliver('B|P1', rssi=-40)
        wand.tick()
    wand.settle(3000)                            # beacon switched off / hidden
    check('reading was dropped', wand.ns['near_rssi'] is None,
          str(wand.ns['near_rssi']))

    wand.command(21, 'NEAR', 0, 5000)
    wand.tick()
    check('NEAR does not pass on a stale reading', wand.state == 'ARMED',
          wand.state)


def main():
    random.seed(1)
    print('Simulating microbit/mb_player.py')
    print('(logic only - thresholds and radio range still need real hardware)')

    for test in (
        test_boot,
        test_resting_when_not_addressed,
        test_button_counting,
        test_window_expiry,
        test_stale_gesture_is_flushed,
        test_wrong_gesture_ignored,
        test_clap_debounce,
        test_own_chirp_not_heard_as_clap,
        test_hold_resets_on_release,
        test_level,
        test_compass_guard,
        test_point_when_calibrated,
        test_acknowledge_stops_resends,
        test_resend_is_capped,
        test_idle_command,
        test_repeat_is_ignored,
        test_corrupt_packets,
        test_beacon_proximity,
        test_beacon_goes_stale,
    ):
        test()

    print('')
    if FAILURES:
        print('{} check(s) failed:'.format(len(FAILURES)))
        for name in FAILURES:
            print('  - {}'.format(name))
        return 1
    print('All checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
