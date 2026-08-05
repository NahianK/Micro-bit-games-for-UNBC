# mb_receiver.py — Flash onto RECEIVER micro:bit(s)
#
# ── WHAT THIS DOES ───────────────────────────────────────────────────────────
# Listens for "PING" broadcasts from a transmitter micro:bit.
# The 5×5 LED matrix fills up from the centre outward as the transmitter
# gets closer. All 25 LEDs glow when the transmitter is right next to you.
#
# Flash this onto ONE or MORE micro:bits.
# Flash mb_transmitter.py onto a different micro:bit and move it around.
# Every receiver reacts independently — no pairing needed.
#
# ── HARDWARE ─────────────────────────────────────────────────────────────────
#   - 1+ × micro:bit (any version) with battery pack or USB
#   - No cables needed after flashing
#
# ── FLASHING ─────────────────────────────────────────────────────────────────
#   1. Go to https://python.microbit.org/v/3
#   2. Paste this entire file into the editor
#   3. Click Send to micro:bit (repeat for each receiver)
#   4. The LED matrix shows 1 centre dot at startup (no signal)
#
# ── LED DISPLAY ──────────────────────────────────────────────────────────────
#   1 dot  (centre only)  = transmitter out of range or very far
#   ~12 dots              = transmitter in the middle distance
#   25 dots (all lit)     = transmitter is RIGHT HERE
#
#   LEDs fill and shrink smoothly as the transmitter moves.
#   Smoothing prevents flickering from radio noise.
#
# ── CALIBRATION ──────────────────────────────────────────────────────────────
#   Adjust RSSI_HOT and RSSI_FLOOR to change how close = "all 25 LEDs".
#
#   HOW TO CALIBRATE:
#     1. Connect a receiver to a computer and open a serial terminal (115200 baud)
#        OR use the micro:bit's REPL in python.microbit.org
#     2. Set DEBUG = True below — RSSI values scroll on the display
#     3. Hold the transmitter at your desired "all LEDs" distance
#        → note the RSSI value (e.g. -48)  → set RSSI_HOT to that value
#     4. Hold the transmitter at your desired "1 LED" distance
#        → note the RSSI value (e.g. -80)  → set RSSI_FLOOR to that value
#     5. Set DEBUG = False and re-flash
#
#   Defaults calibrated indoors with RADIO_POWER = 3:
#     All 25 LEDs = 0 – 0.5 m   (RSSI ≥ -50)
#     1 LED       = ≥ 5 m       (RSSI ≤ -80)
# ─────────────────────────────────────────────────────────────────────────────

from microbit import *
import radio

# ── SETTINGS — must match mb_transmitter.py ──────────────────────────────────
RADIO_GROUP   = 42      # must match transmitter
# ─────────────────────────────────────────────────────────────────────────────

# ── CALIBRATION THRESHOLDS ───────────────────────────────────────────────────
RSSI_HOT   = -50    # dBm — all 25 LEDs (transmitter is very close) ← CALIBRATE
RSSI_FLOOR = -80    # dBm — 1 LED        (transmitter at max range)  ← CALIBRATE
# ─────────────────────────────────────────────────────────────────────────────

# ── SMOOTHING ─────────────────────────────────────────────────────────────────
# Averages the last N RSSI readings to stop the LEDs flickering.
# Higher = smoother but slower to react. 3–6 is a good range.
SMOOTH_WINDOW = 5   # ← increase for smoother display, decrease for faster response
# ─────────────────────────────────────────────────────────────────────────────

# ── DEBUG MODE ────────────────────────────────────────────────────────────────
# Set True to scroll raw RSSI numbers on the display (for calibration).
# Set False for normal LED proximity display.
DEBUG = False
# ─────────────────────────────────────────────────────────────────────────────

# ── LED pixel positions ordered from centre outward ───────────────────────────
# This determines the fill pattern: starts at centre (2,2), spirals outward.
# Do not modify this list unless you want a different fill pattern.
PIXEL_ORDER = [
    (2, 2),
    (2, 1), (2, 3), (1, 2), (3, 2),
    (1, 1), (3, 1), (1, 3), (3, 3),
    (2, 0), (2, 4), (0, 2), (4, 2),
    (1, 0), (3, 0), (0, 1), (4, 1),
    (0, 3), (4, 3), (1, 4), (3, 4),
    (0, 0), (4, 0), (0, 4), (4, 4),
]  # 25 positions total — (col, row)


def proximity_image(rssi):
    """
    Convert an RSSI value into a 5×5 LED image.

    RSSI_FLOOR → 1 LED  (centre dot only — transmitter at max range or beyond)
    RSSI_HOT   → 25 LEDs (all on — transmitter is very close)

    LEDs increase linearly between RSSI_FLOOR and RSSI_HOT.
    Values outside range are clamped (no overflow).

    To change "how close = all 25 LEDs": adjust RSSI_HOT above.
    To change "how far = 1 LED":         adjust RSSI_FLOOR above.
    """
    # ── LED count calculation ─────────────────────────────────────────────────
    ratio = (rssi - RSSI_FLOOR) / (RSSI_HOT - RSSI_FLOOR)  # 0.0=far, 1.0=close
    ratio = max(0.0, min(1.0, ratio))   # clamp to 0–1
    count = 1 + int(ratio * 24)         # 1 to 25 LEDs
    # ─────────────────────────────────────────────────────────────────────────

    grid = [[0] * 5 for _ in range(5)]
    for i in range(count):
        col, row = PIXEL_ORDER[i]
        grid[row][col] = 9
    rows = ["".join(str(grid[r][c]) for c in range(5)) for r in range(5)]
    return Image(":".join(rows))


def smooth(history, new_val):
    """Add new_val to history list, trim to SMOOTH_WINDOW, return average."""
    history.append(new_val)
    if len(history) > SMOOTH_WINDOW:
        history.pop(0)
    return sum(history) // len(history)


# ── Setup ─────────────────────────────────────────────────────────────────────
radio.on()
radio.config(group=RADIO_GROUP)   # power not set here — receiver listens at all levels

rssi_history  = []
current_rssi  = RSSI_FLOOR   # start at floor = 1 LED (no signal)
debug_counter = 0

display.show(proximity_image(current_rssi))   # 1 centre dot on startup

# ── Main loop ─────────────────────────────────────────────────────────────────
while True:
    packet = radio.receive_full()

    if packet:
        raw, rssi_val, _ = packet

        # MicroPython v2 returns bytes with a 3-byte radio header — strip and decode
        if isinstance(raw, bytes):
            text = "".join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
        else:
            text = str(raw).strip()

        if text == "PING":
            current_rssi = smooth(rssi_history, rssi_val)

            if DEBUG:
                # Scroll the raw RSSI on the display for calibration
                debug_counter += 1
                if debug_counter % 3 == 0:   # scroll every 3rd reading (less frantic)
                    display.scroll(str(current_rssi), delay=60)
            else:
                display.show(proximity_image(current_rssi))

    sleep(10)

