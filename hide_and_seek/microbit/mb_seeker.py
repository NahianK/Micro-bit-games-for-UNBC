# mb_seeker.py — Flash onto the Seeker micro:bit (battery powered, free to roam)
#
# ── REUSE NOTE ──────────────────────────────────────────────────────────────
# This file is IDENTICAL in hide_and_seek/ and hide_and_seek_test/.
# The seeker firmware does not change between the test and full versions —
# the seeker doesn't care whether the relay is a hider or a dedicated bridge.
# Reused unchanged from pass_the_ball: PIXEL_ORDER, proximity_image(), smooth(),
#                                       bytes decoding block, radio setup.
# ────────────────────────────────────────────────────────────────────────────
#
# SEEKER BEHAVIOUR:
#   No ID assignment — there is only one seeker.
#   Scrolls "SEEK" on boot to confirm correct firmware.
#   Receives HIDE:H<id> broadcasts from all hiders.
#   Tracks smoothed RSSI per hider separately: { 'H1': rssi, 'H2': rssi, ... }
#   Shows proximity to the NEAREST (strongest RSSI) hider on the LED.
#   After receiving a HIDE packet, re-broadcasts: SEEK:H<id>:<rssi>
#     so the relay/bridge can forward seeker proximity to the computer.
#   Button A (when RSSI > RSSI_HOT): broadcasts TAGGED:H<id>
#     where H<id> is the nearest hider. Dashboard marks that hider as found.
#
# CALIBRATION — REQUIRED EACH SESSION:
#   Because hiding spots change every game, calibrate before each round.
#   RSSI_HOT   = RSSI when seeker is at "found" distance (~0–0.5m from hider)
#   RSSI_WARM  = RSSI at "getting warmer" distance (~1–2m)
#   RSSI_FLOOR = RSSI at maximum useful range (1 LED, ~5m+)

from microbit import *
import radio
import random

# ── constants ────────────────────────────────────────────────────────────────
RADIO_GROUP  = 42
RADIO_POWER  = 7          # seeker broadcasts at full power

# ── CALIBRATION — recalibrate each session (hiding spots change every game) ──
RSSI_HOT   = -50   # dBm — very close, "found" distance  ← CALIBRATE THIS
RSSI_WARM  = -65   # dBm — getting warmer (~1–2m)        ← CALIBRATE THIS
RSSI_FLOOR = -80   # dBm — 1 LED, maximum useful range   ← CALIBRATE THIS
# ─────────────────────────────────────────────────────────────────────────────

SMOOTH_WINDOW = 5   # readings to average per hider (higher = smoother but slower)

# ── radio setup ───────────────────────────────────────────────────────────────
radio.on()
radio.config(group=RADIO_GROUP, power=RADIO_POWER)

display.scroll("SEEK", delay=80)

# ── helpers ───────────────────────────────────────────────────────────────────
# REUSE: smooth(), PIXEL_ORDER, proximity_image() are IDENTICAL across all games.
# Copied directly from pass_the_ball/mb_player.py without modification.

def smooth(history, new_val):
    history.append(new_val)
    if len(history) > SMOOTH_WINDOW:
        history.pop(0)
    return sum(history) // len(history)

# Pixel positions ordered from centre outward — determines LED fill pattern.
# REUSE: identical in mb_player.py, mb_seeker.py across all games.
PIXEL_ORDER = [
    (2, 2),
    (2, 1), (2, 3), (1, 2), (3, 2),
    (1, 1), (3, 1), (1, 3), (3, 3),
    (2, 0), (2, 4), (0, 2), (4, 2),
    (1, 0), (3, 0), (0, 1), (4, 1),
    (0, 3), (4, 3), (1, 4), (3, 4),
    (0, 0), (4, 0), (0, 4), (4, 4),
]

def proximity_image(rssi):
    """
    Map RSSI to a 5x5 LED image that fills outward from the centre.
    RSSI_FLOOR → 1 LED  (centre dot only — hider at max range or beyond)
    RSSI_HOT   → 25 LEDs (all on — hider very close, "found" range)
    LEDs increase linearly. Values outside range are clamped.
    REUSE: identical to pass_the_ball mb_player.py proximity_image().
    """
    # ── LED count calculation — do not modify this formula ───────────────────
    ratio = (rssi - RSSI_FLOOR) / (RSSI_HOT - RSSI_FLOOR)  # 0.0=far, 1.0=close
    ratio = max(0.0, min(1.0, ratio))
    count = 1 + int(ratio * 24)   # 1 to 25

    grid = [[0] * 5 for _ in range(5)]
    for i in range(count):
        col, row = PIXEL_ORDER[i]
        grid[row][col] = 9
    rows = ["".join(str(grid[r][c]) for c in range(5)) for r in range(5)]
    return Image(":".join(rows))

# ── state ─────────────────────────────────────────────────────────────────────
hider_rssi    = {}   # { 'H1': smoothed_rssi, 'H2': smoothed_rssi, ... }
hider_history = {}   # { 'H1': [list of rssi readings], ... }
nearest_hider = None

display.show(proximity_image(RSSI_FLOOR))   # start: 1 centre dot (no signal)

# ── main loop ─────────────────────────────────────────────────────────────────
while True:
    # ── receive hider broadcasts ──────────────────────────────────────────────
    packet = radio.receive_full()
    if packet:
        raw, rssi_val, _ = packet

        # MicroPython v2 bytes decoding — strip 3-byte radio header
        # REUSE: this decoding block is identical in all games using receive_full()
        if isinstance(raw, bytes):
            text = "".join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
        else:
            text = str(raw).strip()

        # ── GAME-SPECIFIC: react to hider broadcasts ──────────────────────────
        if text.startswith("HIDE:"):
            hid = text[5:]   # e.g. "H1", "H2"

            # Initialise history list for newly seen hiders
            if hid not in hider_history:
                hider_history[hid] = []

            # Smooth RSSI per hider separately
            smoothed = smooth(hider_history[hid], rssi_val)
            hider_rssi[hid] = smoothed

            # Find nearest hider (highest/strongest RSSI)
            nearest_hider = max(hider_rssi, key=hider_rssi.get)
            best_rssi     = hider_rssi[nearest_hider]

            # Update LED based on nearest hider proximity
            display.show(proximity_image(best_rssi))

            # Re-broadcast seeker proximity so relay/bridge can forward to computer
            # Format: "SEEK:H<id>:<rssi>" → bridge prints "SEEK:H<id>:<rssi>,<relay_rssi>"
            radio.send("SEEK:{}:{}".format(hid, smoothed))

    # ── tag found: Button A when very close ───────────────────────────────────
    # GAME-SPECIFIC: seeker presses Button A to signal they've found the nearest hider
    if button_a.was_pressed() and nearest_hider is not None:
        if hider_rssi.get(nearest_hider, RSSI_FLOOR) > RSSI_HOT:
            # Broadcast the tagged message — relay/bridge forwards to dashboard
            radio.send("TAGGED:{}".format(nearest_hider))
            # Flash confirmation on screen
            display.show(Image.YES)
            sleep(600)
            display.show(proximity_image(hider_rssi.get(nearest_hider, RSSI_FLOOR)))

    sleep(10)
