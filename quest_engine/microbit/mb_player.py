# mb_player.py - Quest Engine player wand. Flash onto every child's micro:bit.
# Battery powered, carried around. Requires micro:bit V2 (microphone + logo
# touch + speaker are V2-only). Flash with python.microbit.org/v/3, NOT uflash.
#
# ---------------------------------------------------------------------------
# HOW THE GAME WORKS FROM THIS FILE'S POINT OF VIEW
# ---------------------------------------------------------------------------
# A narrator reads an instruction out loud ("three strikes of the blade!").
# The bridge broadcasts a matching challenge. This wand arms EXACTLY the one
# sensor that challenge needs, shows progress on the LEDs, and reports back
# whether the child did it and how many milliseconds they took.
#
# ---------------------------------------------------------------------------
# WIRE FORMAT - keep in sync with computer_app/protocol.py
# ---------------------------------------------------------------------------
#   In    C|<seq>|<verb>|<arg>|<win>|<mask>|<ack>
#   Out   A|<pid>|<seq>|<result>|<ms>|<eid>
#   Out   H|<pid>|<seq>|<flags>
#   In    B|<prop_id>                         (beacon, only used by NEAR)
#
# <arg> means different things per verb: a repetition count, a duration in ms,
# or a compass bearing. See the verb table below.
# <mask> is a bitmask of player ids, so the narrator can call out one child.
# <ack> is which players the bridge has already heard from - we stop resending
# our answer as soon as our own bit shows up in it.
#
# ---------------------------------------------------------------------------
# TWO RULES THAT CAUSE SILENT BUGS IF BROKEN
# ---------------------------------------------------------------------------
# 1. Only poll the sensor the active verb needs. Otherwise a shout satisfies a
#    tilt challenge and nobody can work out why.
# 2. Flush the gesture and sound history when arming (see arm()). Both APIs
#    return everything since the last call, so a shake left over from the
#    PREVIOUS challenge would instantly complete the next one.

from microbit import *
import radio
import music
import random

# ===========================================================================
# TUNING - these are the values to change on real hardware. Everything that
# needs a stopwatch, a tape measure or a noisy room lives here.
# ===========================================================================

RADIO_GROUP = 42
RADIO_POWER = 7

# --- Microphone --- CALIBRATE against your actual PA at performance volume.
# Raise LOUD_THRESHOLD until the narration stops registering as claps.
LOUD_THRESHOLD   = 150    # 0-255, the level a LOUD event fires at
SHOUT_LEVEL      = 140    # 0-255, sustained level that counts as shouting
CLAP_DEBOUNCE_MS = 250    # ignore a second clap inside this window (echoes)
MIC_MUTE_MS      = 400    # deafen ourselves this long after our own chirp,
                          # otherwise the wand hears its own speaker as a clap

# --- Accelerometer ---
LEVEL_TOL   = 250         # milli-g on x and y that still counts as "flat"
BUBBLE_STEP = 300         # milli-g per LED of bubble travel

# --- Compass ---
# OFF by default and deliberately so: compass.calibrate() is a blocking
# tilt-the-board game that takes 20-40 s PER BOARD, which is three minutes of
# five children standing still. Set this True only when you actually want to
# run POINT challenges, and calibrate in the room you will play in - steel and
# rebar shift the readings.
USE_COMPASS    = False
POINT_TOL      = 25       # degrees of slop allowed
POINT_DWELL_MS = 1000     # how long they must hold the bearing

# --- Proximity, for the NEAR verb (needs a prop running mb_prop.py) ---
RSSI_HOT     = -50        # close enough to count as found  <- CALIBRATE
RSSI_FLOOR   = -80        # edge of useful range            <- CALIBRATE
SMOOTH_ALPHA = 0.3        # 0 = never update, 1 = no smoothing
BEACON_STALE_MS = 2000    # forget the beacon if we stop hearing it

# --- Timing ---
HEARTBEAT_MS         = 1000
HEARTBEAT_JITTER     = 200
ANSWER_RESEND_MS     = 400
ANSWER_RESEND_JITTER = 120
MAX_ANSWER_SENDS     = 6
LOOP_SLEEP_MS        = 10
ID_WINDOW_MS         = 5000

# ===========================================================================
# Verb tables
# ===========================================================================

# verb -> accelerometer gesture name.
# WARNING: 'left' and 'right' are defined against the BOARD's axes, which may
# not match how a child instinctively holds a wand. Verify on hardware before
# printing the whiteboard gesture chart, and swap the labels if needed.
GESTURE_FOR = {
    'TILTL':  'left',
    'TILTR':  'right',
    'TILTU':  'up',
    'TILTD':  'down',
    'SHAKE':  'shake',
    'FACEUP': 'face up',
    'FACEDN': 'face down',
}

# Verbs whose progress reads as "n of m done"
COUNT_VERBS = ('BTNA', 'BTNB', 'TILTL', 'TILTR', 'TILTU', 'TILTD',
               'SHAKE', 'FACEUP', 'FACEDN', 'CLAP')

# Verbs whose progress reads as "held for n of m ms" and draw a filling ring.
# LEVEL is also a sustained verb but draws a spirit-level bubble instead, so it
# is handled by render_level() and deliberately not listed here.
TIMED_VERBS = ('SHOUT', 'HOLD')

# ===========================================================================
# LED glyphs. The children's only visual channel, so icons only, never words.
# ===========================================================================

# REUSE: centre-outward fill order, copied verbatim from
# pass_the_ball_test_5_players/microbit/mb_player.py
PIXEL_ORDER = [
    (2, 2),
    (1, 2), (3, 2), (2, 1), (2, 3),
    (1, 1), (3, 1), (1, 3), (3, 3),
    (0, 2), (4, 2), (2, 0), (2, 4),
    (0, 1), (4, 1), (0, 3), (4, 3),
    (1, 0), (3, 0), (1, 4), (3, 4),
    (0, 0), (4, 0), (0, 4), (4, 4),
]

IMG_BLANK = Image('00000:00000:00000:00000:00000')
IMG_IDLE  = Image('00000:00000:00400:00000:00000')   # dim centre pixel
IMG_REST  = Image('30000:00000:00000:00000:00000')   # dim corner: not your turn
# Hollow box, deliberately unlike the tick and the cross: this challenge could
# not be attempted at all, which is a grown-up problem and not the child's fault.
IMG_NOCAL = Image('99999:90009:90009:90009:99999')


def fill_image(n_pixels):
    """Light the first n pixels of PIXEL_ORDER: a centre-outward filling ring."""
    if n_pixels < 0:
        n_pixels = 0
    if n_pixels > 25:
        n_pixels = 25
    grid = [[0] * 5 for _ in range(5)]
    for i in range(n_pixels):
        col, row = PIXEL_ORDER[i]
        grid[row][col] = 9
    return Image(':'.join(
        ''.join(str(grid[r][c]) for c in range(5)) for r in range(5)
    ))


def slots_image(done, total):
    """
    Top row as progress slots: bright for done, dim for still to go.
    "2 of 3 presses" reads instantly without any text.
    """
    if total > 5:
        total = 5
    top = ''
    for i in range(5):
        if i >= total:
            top += '0'
        elif i < done:
            top += '9'
        else:
            top += '3'
    return Image(':'.join((top, '00000', '00000', '00000', '00000')))


def bubble_image(col, row, centred):
    """Spirit-level bubble. Bright when inside tolerance, dim while hunting."""
    grid = [[0] * 5 for _ in range(5)]
    grid[row][col] = 9 if centred else 5
    return Image(':'.join(
        ''.join(str(grid[r][c]) for c in range(5)) for r in range(5)
    ))


# ===========================================================================
# Boot
# ===========================================================================
def assign_id():
    """
    5-second window: Button A steps the id 1-5, Button B confirms early.
    REUSE: same pattern as assign_id() in treasure_hunt/microbit/mb_hunter.py.
    """
    display.scroll('ID?', delay=60, wait=False)
    pid = 0
    deadline = running_time() + ID_WINDOW_MS
    while running_time() < deadline:
        if button_a.was_pressed():
            pid += 1
            if pid > 5:
                pid = 1
            display.show(str(pid))
        if button_b.was_pressed():
            break
        sleep(50)
    return pid if pid > 0 else 1


PLAYER_ID = assign_id()
MY_BIT    = 1 << (PLAYER_ID - 1)

display.scroll('P{}'.format(PLAYER_ID), delay=80)

radio.config(group=RADIO_GROUP, power=RADIO_POWER, queue=8, length=64)
radio.on()

# Logo touch is capacitive by default on V2; set it explicitly so the intent is
# obvious. Capacitive means the child does NOT have to hold a ground pin.
pin_logo.set_touch_mode(pin_logo.CAPACITIVE)

microphone.set_threshold(SoundEvent.LOUD, LOUD_THRESHOLD)

# Compass calibration, only if POINT challenges are wanted. This blocks.
if USE_COMPASS and not compass.is_calibrated():
    display.scroll('CAL', delay=70)
    compass.calibrate()

# ===========================================================================
# State
# ===========================================================================
STATE_IDLE    = 'IDLE'
STATE_RESTING = 'RESTING'    # a challenge is live but not addressed to us
STATE_ARMED   = 'ARMED'
STATE_DONE    = 'DONE'

state = STATE_IDLE

seq  = -1          # challenge sequence number we have applied
verb = 'IDLE'
arg  = 0
win  = 0
mask = 0
ack  = 0

t0        = 0      # when the current challenge was armed
count     = 0      # progress for countable verbs
run_start = None   # when the current sustained run began, for timed verbs
last_clap = 0

result      = ''
result_ms   = 0
event_id    = 0
answer_sends = 0
next_answer  = 0

mic_mute_until = 0
next_heartbeat = 0

near_rssi = None   # smoothed RSSI of the nearest prop beacon
near_last = 0

last_glyph = None  # redraw only when the picture actually changes


# ===========================================================================
# Feedback
# ===========================================================================
def chirp(ok):
    """
    Non-blocking two-note blip. This is how a child knows their action landed,
    since they cannot see the gamemaster's screen.
    """
    global mic_mute_until
    music.play(['E5:2', 'B5:2'] if ok else ['B4:2', 'E4:2'], wait=False)
    mic_mute_until = running_time() + MIC_MUTE_MS


# ===========================================================================
# Radio
# ===========================================================================
def decode(raw):
    """Strip the 3-byte radio header and keep printable ASCII. REUSE: shared."""
    if isinstance(raw, bytes):
        return ''.join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
    return str(raw).strip()


def apply_command(c_seq, c_verb, c_arg, c_win, c_mask, c_ack, now):
    global seq, verb, arg, win, mask, ack, state

    if c_seq == seq:
        ack = c_ack            # same challenge, just a newer ack mask
        return

    seq, verb, arg, win, mask, ack = c_seq, c_verb, c_arg, c_win, c_mask, c_ack

    if verb == 'IDLE':
        state = STATE_IDLE
        return

    if not (mask & MY_BIT):
        # Someone else was called out. Show a dim marker rather than going
        # blank, so the child can tell the wand is alive and simply waiting.
        state = STATE_RESTING
        return

    if verb == 'POINT' and not compass.is_calibrated():
        # Never call compass.heading() uncalibrated - it triggers the blocking
        # calibration game, which would strand the child mid-round.
        arm(now)
        answer('NOCAL', 0)
        return

    arm(now)
    state = STATE_ARMED


def handle_radio(now):
    global near_rssi, near_last
    for _ in range(4):
        packet = radio.receive_full()
        if packet is None:
            return
        raw, rssi, _ = packet
        text = decode(raw)
        if not text:
            continue
        parts = text.split('|')

        if parts[0] == 'C' and len(parts) >= 7:
            try:
                apply_command(int(parts[1]), parts[2], int(parts[3]),
                              int(parts[4]), int(parts[5]), int(parts[6]), now)
            except ValueError:
                pass                    # corrupt packet: ignore, do not crash

        elif parts[0] == 'B':
            if near_rssi is None:
                near_rssi = float(rssi)
            else:
                near_rssi = SMOOTH_ALPHA * rssi + (1.0 - SMOOTH_ALPHA) * near_rssi
            near_last = now


def send_answer(now):
    global answer_sends, next_answer
    radio.send('A|{}|{}|{}|{}|{}'.format(
        PLAYER_ID, seq, result, result_ms, event_id))
    answer_sends += 1
    next_answer = now + ANSWER_RESEND_MS + random.randint(0, ANSWER_RESEND_JITTER)


def send_heartbeat():
    if state == STATE_ARMED:
        flag = 'A'
    elif state == STATE_DONE:
        flag = 'D'
    elif state == STATE_RESTING:
        flag = 'R'
    else:
        flag = 'I'
    radio.send('H|{}|{}|{}'.format(PLAYER_ID, seq, flag))


def answer(res, ms):
    global state, result, result_ms, event_id, answer_sends
    result    = res
    result_ms = int(ms)
    event_id  = (event_id + 1) % 1000
    state     = STATE_DONE
    answer_sends = 0
    send_answer(running_time())
    chirp(res == 'OK')


# ===========================================================================
# Detectors: arm() then poll() until it returns True
# ===========================================================================
def arm(now):
    """Zero the counters and FLUSH sensor history. See rule 2 in the header."""
    global count, run_start, last_clap, t0
    count     = 0
    run_start = None
    last_clap = 0
    t0        = now

    # These calls all return "everything since last time" and clear as they go.
    button_a.get_presses()
    button_b.get_presses()
    accelerometer.get_gestures()
    microphone.was_event(SoundEvent.LOUD)


def _sustain(now, holding, needed):
    """Shared logic for the timed verbs: the run resets the moment they slip."""
    global run_start
    if holding:
        if run_start is None:
            run_start = now
        return (now - run_start) >= needed
    run_start = None
    return False


def point_error():
    """Signed degrees from the target bearing, wraparound-safe."""
    return ((compass.heading() - arg + 180) % 360) - 180


def poll(now):
    global count, last_clap

    need = arg if arg > 0 else 1

    if verb == 'BTNA':
        count += button_a.get_presses()
        return count >= need

    if verb == 'BTNB':
        count += button_b.get_presses()
        return count >= need

    if verb == 'BTNAB':
        return button_a.is_pressed() and button_b.is_pressed()

    if verb in GESTURE_FOR:
        target = GESTURE_FOR[verb]
        for gesture in accelerometer.get_gestures():
            if gesture == target:
                count += 1
        return count >= need

    if verb == 'CLAP':
        # Always drain the event, even while muted, so our own chirp cannot sit
        # in the history and get counted the instant the mute window ends.
        heard = microphone.was_event(SoundEvent.LOUD)
        if heard and now >= mic_mute_until:
            if now - last_clap >= CLAP_DEBOUNCE_MS:
                last_clap = now
                count += 1
        return count >= need

    if verb == 'SHOUT':
        loud = (now >= mic_mute_until
                and microphone.sound_level() >= SHOUT_LEVEL)
        return _sustain(now, loud, max(200, arg))

    if verb == 'HOLD':
        return _sustain(now, pin_logo.is_touched(), max(200, arg))

    if verb == 'LEVEL':
        flat = (abs(accelerometer.get_x()) < LEVEL_TOL
                and abs(accelerometer.get_y()) < LEVEL_TOL)
        return _sustain(now, flat, max(200, arg))

    if verb == 'POINT':
        return _sustain(now, abs(point_error()) <= POINT_TOL, POINT_DWELL_MS)

    if verb == 'NEAR':
        return near_rssi is not None and near_rssi >= RSSI_HOT

    return False


# ===========================================================================
# Rendering
# ===========================================================================
def render(now):
    global last_glyph

    if state == STATE_ARMED:
        if verb in COUNT_VERBS:
            need = arg if arg > 0 else 1
            key  = 'c{}/{}'.format(count, need)
            img  = slots_image(count, need)

        elif verb in TIMED_VERBS:
            need    = max(200, arg)
            held    = 0 if run_start is None else now - run_start
            filled  = int(25 * held / need)
            key     = 't{}'.format(filled)
            img     = fill_image(filled)

        elif verb == 'POINT':
            err = point_error()
            if abs(err) <= POINT_TOL:
                key, img = 'p-ok', Image.YES
            elif err > 0:
                key, img = 'p-w', Image.ARROW_W   # turn anticlockwise
            else:
                key, img = 'p-e', Image.ARROW_E   # turn clockwise

        elif verb == 'BTNAB':
            # Nothing to count; a steady centre dot just says "go".
            key, img = 'hold', IMG_IDLE

        elif verb == 'NEAR':
            if near_rssi is None:
                lit = 0
            elif near_rssi >= RSSI_HOT:
                lit = 25
            elif near_rssi <= RSSI_FLOOR:
                lit = 1
            else:
                ratio = (near_rssi - RSSI_FLOOR) / float(RSSI_HOT - RSSI_FLOOR)
                lit = max(1, int(ratio * 25))
            key, img = 'n{}'.format(lit), fill_image(lit)

        else:
            key, img = 'armed', IMG_IDLE

    elif state == STATE_DONE:
        if result == 'OK':
            key, img = 'ok', Image.YES
        elif result == 'NOCAL':
            key, img = 'nocal', IMG_NOCAL
        else:
            key, img = 'fail', Image.NO

    elif state == STATE_RESTING:
        key, img = 'rest', IMG_REST

    else:
        # Idle: a slow blink so a child can see the wand is awake.
        on = (now // 600) % 2 == 0
        key, img = ('idle-on', IMG_IDLE) if on else ('idle-off', IMG_BLANK)

    if key != last_glyph:
        display.show(img)
        last_glyph = key


# LEVEL wants a live bubble rather than the ring, so it gets its own branch
# ahead of the generic timed rendering above.
def render_level(now):
    global last_glyph
    x = accelerometer.get_x()
    y = accelerometer.get_y()
    centred = abs(x) < LEVEL_TOL and abs(y) < LEVEL_TOL
    col = 2 + max(-2, min(2, int(x / BUBBLE_STEP)))
    row = 2 + max(-2, min(2, int(y / BUBBLE_STEP)))
    key = 'b{},{},{}'.format(col, row, 1 if centred else 0)
    if key != last_glyph:
        display.show(bubble_image(col, row, centred))
        last_glyph = key


# ===========================================================================
# Main loop
#
# One pass lives in tick() rather than inline, so tools/simulate_wand.py can
# drive this exact code on a computer with a stubbed micro:bit API. The
# detectors and the state machine are the fiddly parts of this game, and being
# able to test them without five children in the room is worth the indirection.
# ===========================================================================
def tick(now):
    global near_rssi, answer_sends, next_heartbeat

    handle_radio(now)

    # Forget a stale beacon so NEAR cannot pass on a reading from minutes ago.
    if near_rssi is not None and now - near_last > BEACON_STALE_MS:
        near_rssi = None

    if state == STATE_ARMED:
        if poll(now):
            answer('OK', now - t0)
        elif win > 0 and (now - t0) >= win:
            answer('FAIL', win)

    if state == STATE_ARMED and verb == 'LEVEL':
        render_level(now)
    else:
        render(now)

    if now >= next_heartbeat:
        send_heartbeat()
        next_heartbeat = now + HEARTBEAT_MS + random.randint(0, HEARTBEAT_JITTER)

    # Keep resending the answer until the bridge acknowledges our bit. This is
    # the only retry mechanism there is - micro:bit radio has no ACKs.
    if state == STATE_DONE and answer_sends < MAX_ANSWER_SENDS:
        if ack & MY_BIT:
            answer_sends = MAX_ANSWER_SENDS
        elif now >= next_answer:
            send_answer(now)


display.show(IMG_IDLE)

while True:
    tick(running_time())
    sleep(LOOP_SLEEP_MS)
