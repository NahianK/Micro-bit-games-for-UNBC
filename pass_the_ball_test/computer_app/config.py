# config.py — All tunable settings for the Pass the Ball computer app
#
# Serial port is auto-detected from the Micro:bit's USB vendor/product ID.
# No manual changes needed when switching between Windows and Raspberry Pi.
# Override by setting the MICROBIT_PORT environment variable if needed:
#   Windows  : set MICROBIT_PORT=COM4 && python app.py
#   Linux/Pi : MICROBIT_PORT=/dev/ttyACM1 python app.py

import os
import sys
import serial.tools.list_ports

# ── Serial connection ─────────────────────────────────────────────────────────
# Micro:bit USB identifiers (same on all OS)
_MICROBIT_VID = 0x0D28
_MICROBIT_PID = 0x0204

def _find_serial_port() -> str:
    """Return the first Micro:bit serial port found, or a platform default."""
    # Environment variable override — useful for unusual port numbers
    if "MICROBIT_PORT" in os.environ:
        return os.environ["MICROBIT_PORT"]

    # Auto-detect by USB vendor/product ID
    for port in serial.tools.list_ports.comports():
        if port.vid == _MICROBIT_VID and port.pid == _MICROBIT_PID:
            return port.device

    # Fallback defaults per platform
    if sys.platform.startswith("win"):
        return "COM3"
    return "/dev/ttyACM0"   # Linux / Raspberry Pi

SERIAL_PORT = _find_serial_port()
BAUD_RATE   = 115200

# ── RSSI thresholds (dBm) ─────────────────────────────────────────────────────
# These may need tuning depending on your environment (indoors vs outdoors,
# walls, interference). More negative = weaker signal = further away.
RSSI_HOT  = -50     # possession zone — player is very close to ball (~touching/0.3m)
RSSI_WARM = -65     # in-range but not possessing (~1-2m)

# ── Signal smoothing ──────────────────────────────────────────────────────────
# Number of RSSI readings to average before acting on them.
# Higher = more stable but slower to react. Lower = faster but noisier.
SMOOTH_WINDOW = 5

# ── Player 2 identity ─────────────────────────────────────────────────────────
# The USB-connected micro:bit is always Player 2 in this 3-device setup.
# "BALL,<rssi>" packets received by this device = ball distance at Player 2.
USB_PLAYER_ID = "P2"

# ── Web server ────────────────────────────────────────────────────────────────
# HOST "0.0.0.0" makes the dashboard reachable from any device on the network.
# On Pi B+: open http://<pi-ip-address>:5000 from any phone or laptop.
HOST = "0.0.0.0"
PORT = 5000

# ── Distance estimation (for Hide & Seek / Treasure Hunt) ────────────────────
# Calibrated indoors with RADIO_POWER = 3 on ball micro:bit.
# Formula: distance_m = 10 ** ((RSSI_AT_1M - rssi) / (10 * PATH_LOSS_N))
# Note: indoor multipath makes this ±50% accurate — use zones not exact metres.
#
# Measured RSSI reference points (environment-specific):
#   Touching : -33 dBm
#   0.5m     : -53 dBm
#   1m       : -53 dBm  (RSSI_AT_1M reference)
#   2m       : -70 dBm
#   5m       : -83 dBm
RSSI_AT_1M   = -53    # dBm measured at exactly 1 metre
PATH_LOSS_N  = 2.7    # indoor path loss exponent (free space = 2.0)
# Note: 6m reading was -68 (anomalous wall reflection). Reliable max range ~5m.

# ── Session ───────────────────────────────────────────────────────────────────
# Seconds without a BALL packet from a player before they are considered
# offline. Prevents stale possession state if a micro:bit is switched off.
PLAYER_TIMEOUT_S = 3.0
