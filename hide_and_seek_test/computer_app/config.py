# config.py - Hide and Seek TEST version (3 micro:bits)
# Hider 1 is USB-connected relay. Seeker is free-moving.
# REUSE: same structure as all games. Only thresholds change.
SERIAL_PORT = 'COM3'  # Windows; Raspberry Pi: /dev/ttyACM0
BAUD_RATE = 115200
RSSI_HOT = -50    # found distance  <- CALIBRATE each session
RSSI_WARM = -65   # getting warmer  <- CALIBRATE each session
RSSI_AT_1M = -53  # for distance estimate <- CALIBRATE each session
PATH_LOSS_N = 2.7
SMOOTH_WINDOW = 5
HIDER_TIMEOUT_S = 8.0  # longer timeout - hiders are stationary
HOST = '0.0.0.0'
PORT = 5000
