# config.py - Treasure Hunt TEST (3 micro:bits)
# Treasure 1 is USB-connected relay. Hunters are free-moving.
# REUSE: same structure as all games. Recalibrate RSSI each session.
SERIAL_PORT = 'COM3'          # Raspberry Pi: /dev/ttyACM0
BAUD_RATE = 115200
RSSI_HOT    = -50             # found distance  <- CALIBRATE each session
RSSI_WARM   = -65             # getting warmer  <- CALIBRATE each session
RSSI_AT_1M  = -53             # <- CALIBRATE each session
PATH_LOSS_N = 2.7
SMOOTH_WINDOW = 5
TREASURE_TIMEOUT_S = 10.0
HOST = '0.0.0.0'
PORT = 5000
