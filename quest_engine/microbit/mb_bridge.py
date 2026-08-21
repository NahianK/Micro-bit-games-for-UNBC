# mb_bridge.py - Quest Engine bridge / relay. Flash onto the ONE micro:bit that
# stays plugged into the computer. This device is NOT a player.
#
# ---------------------------------------------------------------------------
# WHAT IS NEW COMPARED WITH THE OTHER GAMES IN THIS REPO
# ---------------------------------------------------------------------------
# The bridges in pass_the_ball / hide_and_seek / treasure_hunt are one-way:
# radio in, print() out. This one is TWO-WAY. It also reads the USB serial port
# so the computer can push challenges out to the wands.
#
# It does three jobs beyond relaying:
#
#   1. REPEAT      Re-broadcasts the active challenge every ~250 ms. The
#                  computer sends each challenge down the wire exactly once;
#                  keeping the repeat loop here means the timing stays tight
#                  and the serial port stays quiet.
#   2. ACKNOWLEDGE Micro:bit radio has no ACKs. As wands answer, we set their
#                  bit in the <ack> field of the repeats. A wand stops resending
#                  its answer the moment it sees its own bit set, so nothing is
#                  lost silently and nobody floods the airwaves.
#   3. STANDALONE  Button A walks through a built-in challenge list and Button B
#                  repeats the current one, so the whole game demos with no
#                  computer at all. This is also the fallback if the serial
#                  downlink misbehaves.
#
# ---------------------------------------------------------------------------
# WIRE FORMAT - keep in sync with computer_app/protocol.py
# ---------------------------------------------------------------------------
#   Downlink   C|<seq>|<verb>|<arg>|<win>|<mask>|<ack>
#   Answer     A|<pid>|<seq>|<result>|<ms>|<eid>
#   Heartbeat  H|<pid>|<seq>|<flags>
#   Beacon     B|<prop_id>
#
# SERIAL OUT
#   "<payload>,<rssi>"   a packet we heard over radio
#   "<payload>"          no comma = the bridge echoing what it just sent,
#                        so the computer knows what went out in standalone mode
#
# SERIAL IN
#   "C|<seq>|<verb>|<arg>|<win>|<mask>" + newline. The <ack> field is optional
#   on the way in and is ignored - we maintain it ourselves.
#
# LED: down arrow = idle and listening. A digit = how many wands have answered
# the current challenge, which is the one number a gamemaster actually needs.
#
# Requires micro:bit V2. Flash with python.microbit.org/v/3 (NOT uflash).

from microbit import *
import radio
import random

# ---------------------------------------------------------------------------
# Radio - must match every other file in this game
# ---------------------------------------------------------------------------
RADIO_GROUP = 42
RADIO_POWER = 7          # max power: the bridge must hear every wand

# How often the active challenge goes back out, plus jitter to avoid colliding
# with the wands' heartbeats and answers.
REPEAT_MS     = 250
REPEAT_JITTER = 60

LOOP_SLEEP_MS = 5

# ---------------------------------------------------------------------------
# Standalone demo sequence: (verb, arg, window_ms, mask)
# mask 31 == 0b11111 == all five wands. Used only by the Button A walkthrough.
# This deliberately touches every sensor so one pass is a full hardware test.
# ---------------------------------------------------------------------------
DEMO = [
    ('BTNA',   3,    6000,  31),   # buttons
    ('BTNB',   2,    6000,  31),   # buttons
    ('TILTL',  1,    6000,  31),   # accelerometer gesture
    ('TILTR',  1,    6000,  31),   # accelerometer gesture
    ('SHAKE',  2,    6000,  31),   # accelerometer gesture
    ('FACEDN', 0,    6000,  31),   # accelerometer orientation
    ('HOLD',   3000, 10000, 31),   # logo touch
    ('CLAP',   2,    8000,  31),   # microphone
    ('SHOUT',  1000, 8000,  31),   # microphone
    ('LEVEL',  2000, 12000, 31),   # accelerometer tilt
    ('IDLE',   0,    0,     31),   # stand down
]

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
active      = None    # (seq, verb, arg, win, mask) or None
ack_mask    = 0       # which players have answered the active challenge
seq_counter = 0       # only used to mint seq numbers in standalone mode
demo_index  = -1

next_repeat = 0
rx_buffer   = b''     # partial serial line from the computer
last_shown  = None    # avoid redrawing the LEDs every loop

radio.config(group=RADIO_GROUP, power=RADIO_POWER, queue=8, length=64)
radio.on()

display.scroll('BRDG', delay=80)
display.show(Image.ARROW_S)      # points down, towards the USB cable


def popcount(mask):
    n = 0
    while mask:
        mask &= mask - 1
        n += 1
    return n


def decode(raw):
    """
    Strip the 3-byte radio header and keep printable ASCII.
    REUSE: identical to the decoding block in every other bridge in this repo.
    """
    if isinstance(raw, bytes):
        return ''.join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
    return str(raw).strip()


def broadcast(echo):
    """Send the active challenge, with the ack mask we have built up so far."""
    if active is None:
        return
    seq, verb, arg, win, mask = active
    msg = 'C|{}|{}|{}|{}|{}|{}'.format(seq, verb, arg, win, mask, ack_mask)
    radio.send(msg)
    if echo:
        # No trailing comma: that is how the computer tells our echoes apart
        # from packets we overheard.
        print(msg)


def set_active(seq, verb, arg, win, mask):
    global active, ack_mask, seq_counter, next_repeat
    active = (seq, verb, arg, win, mask)
    ack_mask = 0
    if seq > seq_counter:
        seq_counter = seq          # never mint a seq the computer already used
    broadcast(True)
    next_repeat = running_time() + REPEAT_MS + random.randint(0, REPEAT_JITTER)


def handle_serial_line(line):
    """Parse one 'C|seq|verb|arg|win|mask[|ack]' line from the computer."""
    parts = line.split('|')
    if len(parts) < 6 or parts[0] != 'C':
        return
    try:
        set_active(int(parts[1]), parts[2],
                   int(parts[3]), int(parts[4]), int(parts[5]))
    except ValueError:
        pass                        # malformed line: ignore rather than crash


def note_answer(payload):
    """A wand answered. Set its ack bit if the answer is for the live challenge."""
    global ack_mask
    if active is None:
        return
    parts = payload.split('|')
    if len(parts) < 3:
        return
    try:
        pid = int(parts[1])
        seq = int(parts[2])
    except ValueError:
        return
    if seq == active[0] and 1 <= pid <= 5:
        ack_mask |= 1 << (pid - 1)


def advance_demo():
    global demo_index, seq_counter
    demo_index = (demo_index + 1) % len(DEMO)
    verb, arg, win, mask = DEMO[demo_index]
    seq_counter += 1
    set_active(seq_counter, verb, arg, win, mask)


def render():
    """Down arrow when idle, otherwise the number of wands that have answered."""
    global last_shown
    if active is None or active[1] == 'IDLE':
        key = 'idle'
    else:
        key = popcount(ack_mask)
    if key == last_shown:
        return
    last_shown = key
    if key == 'idle':
        display.show(Image.ARROW_S)
    else:
        display.show(str(key))


while True:
    now = running_time()

    # --- Uplink: everything we hear on the radio goes to the computer --------
    # Drain a few packets per pass so a burst of answers cannot back up the
    # radio queue while we are sleeping.
    for _ in range(4):
        packet = radio.receive_full()
        if packet is None:
            break
        raw, rssi, _ = packet
        text = decode(raw)
        if not text:
            continue
        print('{},{}'.format(text, rssi))
        if text.startswith('A|'):
            note_answer(text)

    # --- Downlink: challenges pushed from the computer -----------------------
    # NOTE: never call uart.init() here. The default uart IS the USB serial
    # connection that print() writes to, and re-initialising it breaks both.
    if uart.any():
        chunk = uart.read()
        if chunk:
            rx_buffer += chunk
            while b'\n' in rx_buffer:
                line, rx_buffer = rx_buffer.split(b'\n', 1)
                try:
                    handle_serial_line(line.decode('utf-8').strip())
                except Exception:
                    pass            # never let a bad byte take the bridge down
            if len(rx_buffer) > 200:
                rx_buffer = b''     # no newline in sight: drop the garbage

    # --- Repeat the active challenge ----------------------------------------
    if active is not None and now >= next_repeat:
        broadcast(False)
        next_repeat = now + REPEAT_MS + random.randint(0, REPEAT_JITTER)

    # --- Standalone controls ------------------------------------------------
    if button_a.was_pressed():
        advance_demo()
    if button_b.was_pressed() and active is not None:
        # Re-issue the current challenge under a fresh seq so wands re-arm.
        seq_counter += 1
        set_active(seq_counter, active[1], active[2], active[3], active[4])

    render()
    sleep(LOOP_SLEEP_MS)
