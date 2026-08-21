# config.py - Treasure Hunt FULL version
# Up to 8 hunters and 5 treasures. Bridge micro:bit handles USB relay.
# REUSE: same structure as all games. Recalibrate RSSI each session.
#
# Linux / Raspberry Pi OS (this is the only file you must edit when leaving Windows):
#   SERIAL_PORT        = '/dev/ttyACM0'   # or '/dev/ttyUSB0'; Windows uses 'COM3'
#   REACHY_AGENT_HOST  = 'reachy-mini.local'  # .local is reliable on Linux; IP also fine
# See computer_app/README.md and reachy_mini/LINUX.md.
SERIAL_PORT = 'COM3'          # Raspberry Pi / Linux: /dev/ttyACM0
BAUD_RATE = 115200
RSSI_HOT    = -50             # found distance  <- CALIBRATE each session
RSSI_WARM   = -65             # getting warmer  <- CALIBRATE each session
RSSI_AT_1M  = -53             # <- CALIBRATE each session
PATH_LOSS_N = 2.7
SMOOTH_WINDOW = 5
TREASURE_TIMEOUT_S = 10.0
HOST = '0.0.0.0'
PORT = 5000

# ---------------------------------------------------------------------------
# Reachy Mini agent (optional)
#
# >>> REQUIRED TO USE THE ROBOT: set this to True <<<
#   USE_REACHY = True
#
# False = normal Treasure Hunt (no robot). True = when you run app.py the host
# calls the agent /init so the whole Reachy Mini comes up: wake, speaker/voice
# path, and camera tracking — then the setup page can run the identification
# ceremony. The Reachy SDK is NOT installed here; it runs on the robot via SSH.
# ---------------------------------------------------------------------------
USE_REACHY = True

# Network address of the Reachy Mini agent. Pi 5 hotspot IPv4 (10.42.0.83). Prefer IPv4 over reachy-mini.local (avoids fe80::).
# After `python reachy_mini/reachy_cli.py install` (once), the agent auto-starts
# when the robot boots — no manual start needed each session.
REACHY_AGENT_HOST = '10.42.0.83'
REACHY_AGENT_PORT = 7000

# Shared bearer token — must match config.json on the robot.
# Leave empty if no authentication is configured.
REACHY_AGENT_TOKEN = ''

# HTTP timeout (seconds) for health checks and event calls.
# Keep these short so a disconnected robot never delays the game.
# Health is slightly longer than events: hotspot + agent busy during /init
# made 3s flap false "unreachable" while the head was still moving.
REACHY_HEALTH_TIMEOUT_S = 5.0
REACHY_EVENT_TIMEOUT_S  = 2.0
# POST /init does wake + tracker (+ optional robot reconnect). Allow long enough
# for WiFi hotspot flaps during agent load; health stays short above.
REACHY_INIT_TIMEOUT_S   = 90.0
