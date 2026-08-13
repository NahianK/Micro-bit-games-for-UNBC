# config.py — Settings for the 6-micro:bit Pass the Ball app (2–5 players)
#
# Hardware layout:
#   Micro:bit 1 — Bridge  (USB to computer, stationary, not a player)
#   Micro:bit 2 — Ball    (inside/on the physical ball)
#   Micro:bits 3–7 — Players 1–5 (free-moving, no USB needed)
#
# REUSE: This file structure is identical across all games.
#        For other games, only RSSI thresholds need recalibrating.
#
# Moving to Raspberry Pi B+:
#   Change SERIAL_PORT to "/dev/ttyACM0" (run `ls /dev/tty*` to confirm)
#   Everything else stays the same.

# ── Serial connection ─────────────────────────────────────────────────────────
# Port is auto-detected by micro:bit USB VID:PID — no manual changes needed.
# Override: set MICROBIT_PORT env variable if auto-detect picks the wrong port.
#   Windows : set MICROBIT_PORT=COM4 && python app.py
#   Linux   : MICROBIT_PORT=/dev/ttyACM1 python app.py
import os, sys, serial.tools.list_ports as _lp

def _find_serial_port():
    if "MICROBIT_PORT" in os.environ:
        return os.environ["MICROBIT_PORT"]
    for p in _lp.comports():
        if p.vid == 0x0D28 and p.pid == 0x0204:
            return p.device
    return "COM3" if sys.platform.startswith("win") else "/dev/ttyACM0"

SERIAL_PORT = _find_serial_port()
BAUD_RATE   = 115200

# ── RSSI thresholds (dBm) ─────────────────────────────────────────────────────
# ← CALIBRATE THESE after outdoor recalibration (see mb_player.py for method)
# More negative = weaker signal = further away.
# Calibrated indoors Aug 2026 with RADIO_POWER=3 on ball micro:bit.
RSSI_HOT  = -50     # possession zone (~touching / 0–0.5m)   ← CALIBRATE THIS
RSSI_WARM = -65     # outer range (~1–2m)                    ← CALIBRATE THIS

# ── Distance estimation (for Hide & Seek / Treasure Hunt) ────────────────────
# Formula: distance_m = 10 ** ((RSSI_AT_1M - rssi) / (10 * PATH_LOSS_N))
# Accurate to ±50% indoors — use zones not exact metres.
# Measured RSSI reference points (indoor, Aug 2026):
#   Touching : -33 dBm
#   0.5m     : -53 dBm
#   1m       : -53 dBm  ← RSSI_AT_1M reference
#   2m       : -70 dBm
#   5m       : -83 dBm
RSSI_AT_1M  = -53   # dBm at 1 metre  ← CALIBRATE THIS
PATH_LOSS_N = 2.7   # indoor path loss exponent (free space = 2.0)

# ── Signal smoothing ──────────────────────────────────────────────────────────
# Number of RSSI readings to average. Higher = smoother but slower to react.
SMOOTH_WINDOW = 5

# ── Session ───────────────────────────────────────────────────────────────────
# Seconds without data before a player is shown as offline on the dashboard.
PLAYER_TIMEOUT_S = 3.0

# ── Web server ────────────────────────────────────────────────────────────────
# "0.0.0.0" makes the dashboard reachable from any device on the same network.
# On Raspberry Pi B+: open http://<pi-ip>:5000 from any phone or laptop.
HOST = "0.0.0.0"
PORT = 5000
