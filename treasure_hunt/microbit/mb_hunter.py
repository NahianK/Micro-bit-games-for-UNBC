# mb_hunter.py — Treasure Hunt hunter micro:bit
# Flash onto hunter micro:bits (battery powered, free to move).
# RADIO_GROUP=42, RADIO_POWER=7
#
# ── REGISTRATION (Reachy mode, micro:bit V2 only) ────────────────────────────
# When the PC sends REG_START (RG|S|<token>) via the bridge, this hunter
# enters identification mode. Touch the gold logo pad once to latch ready;
# you do not need to keep holding it — a diamond appears on the display.
# The PC assigns a random 3-button code; the hunter enters it with A and B,
# and the PC confirms a permanent hunter ID.
#
# Registration states:
#   None          — normal gameplay (no registration running)
#   'READY'       — waiting for logo touch; latched hunters show a diamond
#                   and send READY every ~300 ms
#   'ENTERING'    — code assigned; polling A/B for the 3-button code
#   'WAITING_ACK' — code sent; waiting for PC confirmation
#
# ── NORMAL PLAY ──────────────────────────────────────────────────────────────
# Without registration, the 5-second boot window assigns an ID (H1..H8)
# by Button A presses, confirmed by Button B. Nothing else changes.
#
# CONTROLS (normal play):
#   Button A — mute/unmute proximity sound
#   Button B — CLAIM (two-step find: Hunter B, then Treasure B)
#   Button A + B (registration enter) — enter code digits during identification

import radio
import music
import microbit
from microbit import display, button_a, button_b, Image, sleep, running_time, pin_logo
import random

# ---------------------------------------------------------------------------
# Calibration constants
# ---------------------------------------------------------------------------
RSSI_HOT   = -50
RSSI_WARM  = -65
RSSI_FLOOR = -80

RADIO_GROUP = 42
RADIO_POWER = 7

SMOOTH_ALPHA         = 0.3
REBROADCAST_INTERVAL = 500

# ---------------------------------------------------------------------------
# Sound
# ---------------------------------------------------------------------------
sound_enabled = True

BEEP_DURATION = 40
BEEP_COLD_MS  = 1200
BEEP_WARM_MS  = 400
BEEP_HOT_MS   = 120

PITCH_COLD  = 262
PITCH_WARM  = 440
PITCH_HOT   = 880

FOUND_JINGLE = ['C4:1', 'E4:1', 'G4:1', 'C5:2']
START_JINGLE = ['G4:2', 'C5:2', 'E5:2', 'G5:3']


def current_sound_params(rssi):
    if not sound_enabled:
        return None
    if rssi is None or rssi <= RSSI_FLOOR:
        return None
    if rssi >= RSSI_HOT:
        return (PITCH_HOT,  BEEP_HOT_MS)
    if rssi >= RSSI_WARM:
        return (PITCH_WARM, BEEP_WARM_MS)
    return (PITCH_COLD, BEEP_COLD_MS)


# ---------------------------------------------------------------------------
# Proximity LED
# ---------------------------------------------------------------------------
PIXEL_ORDER = [
    (2, 2),
    (1, 2), (3, 2), (2, 1), (2, 3),
    (1, 1), (3, 1), (1, 3), (3, 3),
    (0, 2), (4, 2), (2, 0), (2, 4),
    (0, 1), (4, 1), (0, 3), (4, 3),
    (1, 0), (3, 0), (1, 4), (3, 4),
    (0, 0), (4, 0), (0, 4), (4, 4),
]


def proximity_image(rssi):
    if rssi is None or rssi <= RSSI_FLOOR:
        n_pixels = 1
    elif rssi >= RSSI_HOT:
        n_pixels = 25
    else:
        ratio = (rssi - RSSI_FLOOR) / float(RSSI_HOT - RSSI_FLOOR)
        n_pixels = max(1, int(ratio * 25))
    pixels = [[0] * 5 for _ in range(5)]
    for i, (col, row) in enumerate(PIXEL_ORDER):
        pixels[row][col] = 9 if i < n_pixels else 0
    rows = [''.join(str(pixels[r][c]) for c in range(5)) for r in range(5)]
    return Image(':'.join(rows))


# ---------------------------------------------------------------------------
# Boot ID assignment (non-Reachy path — 5-second window)
# ---------------------------------------------------------------------------
def assign_id():
    display.scroll('H?', delay=60, wait=False)
    press_count = 0
    deadline = running_time() + 5000
    while running_time() < deadline:
        if button_a.was_pressed():
            press_count += 1
            display.show(str(press_count))
        if button_b.was_pressed():
            break
    # Allow up to H8 for compatibility with Reachy sessions
    hunter_num = max(1, min(8, press_count)) if press_count > 0 else 1
    return 'H{}'.format(hunter_num)


HUNTER_ID = assign_id()

# Boot nonce — a short random token that uniquely identifies this device
# within a registration session. Generated once at boot using the hardware
# random source (micro:bit V2 has True RNG; random.randint uses it on V2).
_NONCE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789'
NONCE = ''.join(random.choice(_NONCE_CHARS) for _ in range(4))

display.scroll('HUNT', delay=80)
display.scroll(HUNTER_ID, delay=80)

# ---------------------------------------------------------------------------
# Radio setup
# ---------------------------------------------------------------------------
radio.config(group=RADIO_GROUP, power=RADIO_POWER, queue=8, length=64)
radio.on()

# Gold logo is capacitive on V2. Without this, is_touched() uses resistive
# mode and waits for a closed circuit to GND — a finger never triggers it.
try:
    pin_logo.set_touch_mode(pin_logo.CAPACITIVE)
except Exception:
    pass

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
rssi_per_treasure  = {}
heard_at           = {}      # last TRS time per treasure (ms)
found_ids          = {}      # treasures already FOUND — ignore for ranging
STALE_MS           = 2500
nearest_treasure   = None
nearest_rssi       = None
next_rebroadcast   = 0
claimed            = False
claim_time         = 0
last_beep          = 0

# Registration state
reg_state          = None    # None | 'READY' | 'ENTERING' | 'WAITING_ACK'
reg_token          = None
reg_code           = ''       # button presses entered so far
reg_expected_code  = None
next_ready_send    = 0        # when to next broadcast READY
ready_latched      = False    # one logo touch — no need to keep holding
waiting_ack_since  = 0        # ms when we entered WAITING_ACK
last_code_resend   = 0        # ms when we last re-sent RG|C
WAITING_ACK_RESEND_MS = 800   # re-send code if RG|K was missed
WAITING_ACK_GIVEUP_MS = 12000 # fall back to code entry after this

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def decode_packet(packet):
    if packet is None:
        return None, None
    raw, rssi_val, _ = packet
    if isinstance(raw, bytes):
        text = ''.join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
    else:
        text = str(raw).strip()
    return text, rssi_val


def smooth(old, new_val, alpha=SMOOTH_ALPHA):
    if old is None:
        return float(new_val)
    return alpha * float(new_val) + (1.0 - alpha) * old


def refresh_nearest(now):
    """Drop found/stale treasures, then pick the strongest remaining RSSI."""
    global nearest_treasure, nearest_rssi
    for tid in list(rssi_per_treasure):
        if tid in found_ids or now - heard_at.get(tid, 0) > STALE_MS:
            del rssi_per_treasure[tid]
            if tid in heard_at:
                del heard_at[tid]
    best_id = best_rssi = None
    for tid, r in rssi_per_treasure.items():
        if best_rssi is None or r > best_rssi:
            best_rssi = r
            best_id   = tid
    nearest_treasure = best_id
    nearest_rssi     = best_rssi


def mark_found(tid, now):
    found_ids[tid] = True
    if tid in rssi_per_treasure:
        del rssi_per_treasure[tid]
    if tid in heard_at:
        del heard_at[tid]
    refresh_nearest(now)


def show_code_briefly(code):
    """Flash each button in the 3-char code, then show diamond (ready to enter)."""
    for ch in code:
        display.show(ch)
        sleep(350)
    display.show(Image.DIAMOND)


def logo_is_touched():
    """True when the gold pad is held. Safe on firmware that lacks pin_logo."""
    try:
        return bool(pin_logo.is_touched())
    except Exception:
        return False


def play_start_beep():
    """Ascending jingle when the host signals game start (RG|G)."""
    music.play(START_JINGLE, wait=False)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
while True:
    now = running_time()

    # =======================================================================
    # REGISTRATION HANDLING
    # =======================================================================
    packet = radio.receive_full()
    text, rssi_val = decode_packet(packet)

    if text and text.startswith('RG|'):
        parts = text.split('|')
        rg_type = parts[1] if len(parts) > 1 else ''

        if rg_type == 'S' and len(parts) >= 3:
            # REG_START — enter registration mode
            reg_token = parts[2]
            reg_state = 'READY'
            reg_code  = ''
            reg_expected_code = None
            next_ready_send   = 0
            ready_latched     = False
            waiting_ack_since = 0
            last_code_resend  = 0
            display.show(Image.DIAMOND_SMALL)

        elif rg_type == 'E':
            # Session ended / cancelled — return to normal play
            if reg_state is not None:
                reg_state = None
                display.show(proximity_image(nearest_rssi))

        elif rg_type == 'G':
            # Game start — play go-jingle and leave registration mode
            reg_state = None
            reg_token = None
            play_start_beep()
            display.show(Image.HAPPY)

        elif rg_type == 'A' and len(parts) >= 5 and reg_state in ('READY', 'ENTERING'):
            # ASSIGN: check nonce and token match us
            if parts[2] == NONCE and parts[3] == reg_token:
                reg_expected_code = parts[4].upper()
                reg_code = ''
                reg_state = 'ENTERING'
                show_code_briefly(reg_expected_code)

        elif rg_type == 'K' and len(parts) >= 4 and reg_state == 'WAITING_ACK':
            # ACK — check nonce and adopt new hunter ID
            if parts[2] == NONCE:
                HUNTER_ID = parts[3]
                radio.send('RG|O|{}|{}'.format(NONCE, HUNTER_ID))
                reg_state = None
                display.scroll(HUNTER_ID, delay=80)
                display.show(proximity_image(nearest_rssi))

    # Poll the logo every loop — not only when no radio packet arrived.
    # Other hunters' READY packets used to starve this check (elif after RG|).
    if reg_state == 'READY':
        if logo_is_touched():
            ready_latched = True
        if ready_latched:
            display.show(Image.DIAMOND)
            if now >= next_ready_send:
                radio.send('RG|R|{}|{}'.format(NONCE, reg_token))
                next_ready_send = now + 300
        else:
            display.show(Image.DIAMOND_SMALL)
        sleep(20)
        continue

    # =======================================================================
    # NORMAL GAMEPLAY (skipped during registration states)
    # =======================================================================
    if reg_state is None:
        # Handle non-RG packets for proximity / found
        if text and text.startswith('FOUND:'):
            parts2 = text.split(':')
            if len(parts2) == 3:
                mark_found(parts2[1], now)
                display.show(proximity_image(nearest_rssi))
        elif text and text.startswith('TRS:'):
            parts2 = text.split(':')
            if len(parts2) == 2:
                t_id = parts2[1]
                if t_id not in found_ids:
                    old = rssi_per_treasure.get(t_id)
                    rssi_per_treasure[t_id] = smooth(old, rssi_val)
                    heard_at[t_id] = now
                refresh_nearest(now)
                if now >= next_rebroadcast and nearest_treasure is not None:
                    msg = 'HUNT:{}:{}:{}'.format(HUNTER_ID, nearest_treasure,
                                                  int(nearest_rssi))
                    radio.send(msg)
                    next_rebroadcast = now + REBROADCAST_INTERVAL
                display.show(proximity_image(nearest_rssi))
        else:
            refresh_nearest(now)

        # Button A: mute toggle
        if button_a.was_pressed():
            sound_enabled = not sound_enabled
            if sound_enabled:
                music.pitch(880, 150, wait=False)
            else:
                music.stop()
                display.show(Image.NO)
                sleep(400)
            display.show(proximity_image(nearest_rssi))

        # Button B: CLAIM
        if button_b.was_pressed():
            radio.send('CLAIM:{}'.format(HUNTER_ID))
            claimed    = True
            claim_time = now
            music.play(FOUND_JINGLE, wait=False)
            display.scroll('FIND!', delay=80, wait=False)

        # Proximity sound
        sound = current_sound_params(nearest_rssi)
        if sound:
            pitch_hz, interval_ms = sound
            if now - last_beep >= interval_ms:
                music.pitch(pitch_hz, BEEP_DURATION, wait=False)
                last_beep = now

    # =======================================================================
    # Button handling during REGISTRATION
    # =======================================================================
    else:
        if reg_state == 'ENTERING':
            display.show(Image.DIAMOND)
            pressed = None
            if button_a.was_pressed():
                pressed = 'A'
            elif button_b.was_pressed():
                pressed = 'B'

            if pressed is not None:
                reg_code += pressed
                display.show(pressed)
                sleep(150)
                if len(reg_code) == 3:
                    radio.send('RG|C|{}|{}|{}'.format(NONCE, reg_token, reg_code))
                    reg_state = 'WAITING_ACK'
                    waiting_ack_since = now
                    last_code_resend = now
                    display.show(Image.YES)
                else:
                    display.show(Image.DIAMOND)

        elif reg_state == 'WAITING_ACK':
            # PC may miss RG|C or RG|K on radio — retry code, accept late RG|K
            if now - waiting_ack_since > WAITING_ACK_GIVEUP_MS:
                reg_state = 'ENTERING'
                reg_code = ''
                display.show(Image.DIAMOND)
            elif now - last_code_resend >= WAITING_ACK_RESEND_MS:
                radio.send('RG|C|{}|{}|{}'.format(NONCE, reg_token, reg_code))
                last_code_resend = now

    sleep(5)
