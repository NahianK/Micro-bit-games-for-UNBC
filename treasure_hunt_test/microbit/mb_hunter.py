# mb_hunter.py - Treasure Hunt (test + full version - firmware is identical)
# Flash onto hunter micro:bits (battery powered, free to move).
# REUSE: this file is identical in treasure_hunt full version.
# RADIO_GROUP=42, RADIO_POWER=7

import radio
import microbit
from microbit import display, button_a, button_b, Image, sleep, running_time
import random

# ---------------------------------------------------------------------------
# Calibration constants - CALIBRATE THIS each session with actual hardware
# ---------------------------------------------------------------------------
RSSI_HOT   = -50   # very close / found  <- CALIBRATE THIS each session
RSSI_WARM  = -65   # getting warmer       <- CALIBRATE THIS each session
RSSI_FLOOR = -80   # max useful range     <- CALIBRATE THIS each session

RADIO_GROUP = 42
RADIO_POWER = 7    # full power for hunters (free-moving)

SMOOTH_ALPHA   = 0.3   # exponential smoothing factor (0=no update, 1=instant)
REBROADCAST_INTERVAL = 500   # ms between HUNT re-broadcasts

# ---------------------------------------------------------------------------
# Proximity LED: centre-outward fill (5×5 grid)
# Same pattern as pass_the_ball proximity display.
# PIXEL_ORDER: index 0 = centre pixel, outward rings after
# ---------------------------------------------------------------------------
PIXEL_ORDER = [
    (2, 2),                                          # centre
    (1, 2), (3, 2), (2, 1), (2, 3),                 # ring 1 (cardinal)
    (1, 1), (3, 1), (1, 3), (3, 3),                 # ring 1 (diagonal)
    (0, 2), (4, 2), (2, 0), (2, 4),                 # ring 2 (cardinal)
    (0, 1), (4, 1), (0, 3), (4, 3),
    (1, 0), (3, 0), (1, 4), (3, 4),
    (0, 0), (4, 0), (0, 4), (4, 4),                 # corners last
]

def proximity_image(rssi):
    """
    Return a 5×5 Image representing proximity.
    RSSI >= RSSI_HOT  → all 25 pixels lit (found!)
    RSSI <= RSSI_FLOOR → 1 pixel (faint signal)
    Linear interpolation between FLOOR and HOT.
    """
    if rssi is None or rssi <= RSSI_FLOOR:
        n_pixels = 1
    elif rssi >= RSSI_HOT:
        n_pixels = 25
    else:
        ratio = (rssi - RSSI_FLOOR) / float(RSSI_HOT - RSSI_FLOOR)
        n_pixels = max(1, int(ratio * 25))

    pixels = [[0] * 5 for _ in range(5)]
    for i, (col, row) in enumerate(PIXEL_ORDER):
        if i < n_pixels:
            pixels[row][col] = 9
        else:
            pixels[row][col] = 0

    rows = ["".join(str(pixels[r][c]) for c in range(5)) for r in range(5)]
    return Image(":".join(rows))

# ---------------------------------------------------------------------------
# ID assignment via Button A presses during 5-second boot window
# Button B confirms immediately (or wait 5 s for default H1)
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
    hunter_num = max(1, min(5, press_count)) if press_count > 0 else 1
    return 'H{}'.format(hunter_num)

HUNTER_ID = assign_id()

# Boot animation
display.scroll('HUNT', delay=80)
display.scroll(HUNTER_ID, delay=80)

# ---------------------------------------------------------------------------
# Radio setup
# ---------------------------------------------------------------------------
radio.config(group=RADIO_GROUP, power=RADIO_POWER, queue=8, length=64)
radio.on()

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
# Smoothed RSSI per treasure: { 'T1': -75.0, 'T2': -80.0, ... }
rssi_per_treasure = {}

# Nearest treasure tracking
nearest_treasure  = None
nearest_rssi      = None

# Re-broadcast scheduling
next_rebroadcast  = 0

# Claim state
claimed           = False
claim_time        = 0

# ---------------------------------------------------------------------------
# Helper: MicroPython v2 bytes decoding (REQUIRED for receive_full)
# ---------------------------------------------------------------------------
def decode_packet(packet):
    """Return (text, rssi) or (None, None) if packet is invalid."""
    if packet is None:
        return None, None
    raw, rssi_val, _ = packet
    if isinstance(raw, bytes):
        text = "".join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
    else:
        text = str(raw).strip()
    return text, rssi_val

# ---------------------------------------------------------------------------
# Helper: exponential smoothing
# ---------------------------------------------------------------------------
def smooth(old, new_val, alpha=SMOOTH_ALPHA):
    if old is None:
        return float(new_val)
    return alpha * float(new_val) + (1.0 - alpha) * old

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
while True:
    now = running_time()

    # --- Receive radio packets ---
    packet = radio.receive_full()
    text, rssi_val = decode_packet(packet)

    if text and text.startswith('TRS:'):
        # Format: TRS:T<id>
        parts = text.split(':')
        if len(parts) == 2:
            t_id = parts[1]   # e.g. 'T1'
            old  = rssi_per_treasure.get(t_id)
            rssi_per_treasure[t_id] = smooth(old, rssi_val)

            # Determine nearest (strongest RSSI)
            best_id   = None
            best_rssi = None
            for tid, r in rssi_per_treasure.items():
                if best_rssi is None or r > best_rssi:
                    best_rssi = r
                    best_id   = tid
            nearest_treasure = best_id
            nearest_rssi     = best_rssi

            # Re-broadcast proximity to nearest treasure only
            if now >= next_rebroadcast and nearest_treasure is not None:
                msg = 'HUNT:{}:{}:{}'.format(HUNTER_ID, nearest_treasure, int(nearest_rssi))
                radio.send(msg)
                next_rebroadcast = now + REBROADCAST_INTERVAL

            # Update LED
            display.show(proximity_image(nearest_rssi))

    # --- Button B: CLAIM (only when close enough) ---
    if button_b.was_pressed():
        rssi_ok = (nearest_rssi is not None and nearest_rssi > RSSI_WARM)
        if rssi_ok or True:   # allow claim regardless; treasure validates proximity
            radio.send('CLAIM:{}'.format(HUNTER_ID))
            claimed   = True
            claim_time = now
            display.scroll('FIND!', delay=80, wait=False)
