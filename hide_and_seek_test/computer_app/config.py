# config.py - Hide and Seek TEST version (3 micro:bits)
# Hider 1 is USB-connected relay. Seeker is free-moving.
# REUSE: same structure as all games. Only thresholds change.
#
# Port is auto-detected by micro:bit USB VID:PID — no manual changes needed.
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
BAUD_RATE = 115200
RSSI_HOT = -50    # found distance  <- CALIBRATE each session
RSSI_WARM = -65   # getting warmer  <- CALIBRATE each session
RSSI_AT_1M = -53  # for distance estimate <- CALIBRATE each session
PATH_LOSS_N = 2.7
SMOOTH_WINDOW = 5
HIDER_TIMEOUT_S = 8.0  # longer timeout - hiders are stationary
HOST = '0.0.0.0'
PORT = 5000
