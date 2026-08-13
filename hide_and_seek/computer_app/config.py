# config.py — Hide and Seek full version (bridge + seeker + 1–5 hiders)
#
# ── REUSE NOTE ──────────────────────────────────────────────────────────────
# Structure identical to hide_and_seek_test/computer_app/config.py and
# pass_the_ball_test_5_players/computer_app/config.py.
# Only RSSI thresholds need updating — and they MUST be recalibrated each
# session because hiding spots and room geometry change every game.
# ────────────────────────────────────────────────────────────────────────────
#
# Moving to Raspberry Pi B+:
#   Change SERIAL_PORT to "/dev/ttyACM0"  (or /dev/ttyACM1 if ACM0 is taken)
#   Run: python app.py   (same command on Pi)

# ── Serial connection ─────────────────────────────────────────────────────────
# Port is auto-detected by micro:bit USB VID:PID — works on Windows and Linux.
# Override: set MICROBIT_PORT env variable if auto-detect picks the wrong port.
import os, sys, serial.tools.list_ports as _lp

def _find_serial_port():
    if "MICROBIT_PORT" in os.environ:
        return os.environ["MICROBIT_PORT"]
    for p in _lp.comports():
        if p.vid == 0x0D28 and p.pid == 0x0204:
            return p.device
    return "COM3" if sys.platform.startswith("win") else "/dev/ttyACM0"

SERIAL_PORT = _find_serial_port()
                          # Raspberry Pi: typically /dev/ttyACM0
BAUD_RATE   = 115200

# ── RSSI thresholds — RECALIBRATE EACH SESSION ───────────────────────────────
# Run diagnose_serial.py before each game with a hider at the hiding spot.
# Walk toward them, note the RSSI values, and update these three constants.
RSSI_HOT  = -50     # "found" distance (arm's length from hider) ← CALIBRATE
RSSI_WARM = -65     # "getting warmer"                           ← CALIBRATE

# ── Distance estimation ───────────────────────────────────────────────────────
RSSI_AT_1M  = -53   # dBm at 1 metre from hider  ← CALIBRATE each session
PATH_LOSS_N = 2.7   # indoor path loss exponent

# ── Signal smoothing ──────────────────────────────────────────────────────────
SMOOTH_WINDOW = 5

# ── Hider timeout ─────────────────────────────────────────────────────────────
HIDER_TIMEOUT_S = 8.0   # longer than player timeout — hiders are stationary

# ── Web server ────────────────────────────────────────────────────────────────
HOST = '0.0.0.0'
PORT = 5000
