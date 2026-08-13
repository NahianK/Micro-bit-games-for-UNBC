# config.py - Treasure Hunt FULL version
# Up to 5 hunters and 5 treasures. Bridge micro:bit handles USB relay.
# REUSE: same structure as all games. Recalibrate RSSI each session.
#
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
BAUD_RATE = 115200
RSSI_HOT    = -50             # found distance  <- CALIBRATE each session
RSSI_WARM   = -65             # getting warmer  <- CALIBRATE each session
RSSI_AT_1M  = -53             # <- CALIBRATE each session
PATH_LOSS_N = 2.7
SMOOTH_WINDOW = 5
TREASURE_TIMEOUT_S = 10.0
HOST = '0.0.0.0'
PORT = 5000
