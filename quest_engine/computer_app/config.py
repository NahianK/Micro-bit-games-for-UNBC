# config.py - Quest Engine computer-side settings.
# REUSE: same structure as every other game config in this repo.

# ---------------------------------------------------------------------------
# Serial link to the bridge micro:bit
# ---------------------------------------------------------------------------
SERIAL_PORT = 'COM3'          # Raspberry Pi: '/dev/ttyACM0' (run `ls /dev/tty*`)
BAUD_RATE   = 115200

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
ACTIVE_PLAYERS = 5            # wands in play, 1-5. With 6 boards: 1 bridge + 5.
PACK           = 'dragon'     # 'dragon' or 'space'
DIFFICULTY     = 'normal'     # 'easy' | 'normal' | 'hard' - scales answer windows

# Answer windows are multiplied by this. Easy gives children more time.
DIFFICULTY_WINDOW_SCALE = {
    'easy':   1.5,
    'normal': 1.0,
    'hard':   0.65,
}

# How long to keep collecting after a challenge window closes, so late radio
# packets still land before we score the round.
ANSWER_GRACE_S = 0.6

# A wand is shown offline in the roster after this long with no heartbeat.
# Heartbeats arrive about every second.
PLAYER_TIMEOUT_S = 4.0

# ---------------------------------------------------------------------------
# Optional hardware. Scenario steps that declare "requires": "compass" or
# "requires": "prop" are SKIPPED unless the matching flag is True here, so a
# pack can ship steps you are not set up for without handing the children a
# challenge that cannot possibly succeed.
# ---------------------------------------------------------------------------

# Compass / POINT challenges. Turning this on means also setting
# USE_COMPASS = True in microbit/mb_player.py and calibrating every wand, which
# is a blocking 20-40 s per board. Indoors, expect steel and rebar to distort
# headings; calibrate in the room you will actually play in.
USE_COMPASS = False

# Prop beacon / NEAR challenges. Needs a spare micro:bit running mb_prop.py.
# With only six boards that means 1 bridge + 4 wands + 1 prop.
USE_PROP = False

# ---------------------------------------------------------------------------
# Proximity, for the NEAR verb (needs a prop micro:bit running mb_prop.py)
# ---------------------------------------------------------------------------
RSSI_HOT   = -50              # found  <- CALIBRATE each session
RSSI_FLOOR = -80              # edge of useful range  <- CALIBRATE each session

# ---------------------------------------------------------------------------
# Audio. Narration is pre-rendered to WAV by tools/build_voice.py; at runtime
# we only play files, which is why this works on a Raspberry Pi B+.
# ---------------------------------------------------------------------------
AUDIO_ENABLED = True
VOICE_DIR     = 'static/voice'   # <VOICE_DIR>/<pack>/<line_id>.wav
SFX_DIR       = 'static/sfx'
NARRATION_VOLUME = 0.9
SFX_VOLUME       = 0.7

# Microphone challenges are impossible while the PA is still talking, because
# the wands hear the narration. The engine goes silent for this long before
# opening a CLAP or SHOUT window.
MIC_QUIET_LEAD_S = 0.4

# ---------------------------------------------------------------------------
# Reachy Mini narrator robot (optional)
#
# The robot is a face for the narrator, not a new game mechanic. With
# USE_ROBOT = False everything below is ignored and the game runs exactly as it
# did before: narration through the computer's speakers via pygame.
#
# Narration is still pre-rendered by tools/build_voice.py. The robot plays the
# same WAV files; it does not synthesise anything.
# ---------------------------------------------------------------------------
USE_ROBOT = False

# Wireless Reachy Mini runs its own daemon on the onboard Pi. 'auto' tries
# localhost first, then falls back to this host, so it also works unchanged if
# you ever run the game ON the robot. Use the IP if .local does not resolve.
ROBOT_HOST         = '10.38.22.140'   # reachy-mini.local often fails on Windows
ROBOT_PORT         = 8000
ROBOT_CONNECT_MODE = 'network'       # 'auto' | 'network' | 'localhost_only'
ROBOT_TIMEOUT_S    = 15.0            # WebRTC media init needs more than 5s

# Narration out of the robot's speaker instead of the computer's. Turn this off
# to keep the PA for narration while the robot still moves and reacts - useful
# if the robot turns out too quiet for the room.
#
# WARNING: the robot's speaker sits about a metre from the children rather than
# across the room, so it changes what the wands' microphones hear. Re-tune
# LOUD_THRESHOLD in microbit/mb_player.py after turning this on. See the
# "Microphone" part of the Tuning section in the README.
ROBOT_NARRATES = True

# Audio-reactive head movement. The SDK analyses whatever is played through the
# robot and nods the head in time with it, so the narrator visibly talks
# without a single line of hand-authored motion.
ROBOT_WOBBLE = True

# Upload every narration WAV to the robot when a pack loads. Playing a local
# file over the network uploads it first, so without this the FIRST time each
# line is spoken it stalls for the transfer - which is exactly the moment a
# room full of children is waiting.
ROBOT_PRELOAD_VOICES = True

# The SDK's play_sound is fire-and-forget: it reports neither progress nor
# completion. We work out how long a line lasts by reading the WAV header and
# waiting that long, plus this much slack for network and buffering.
ROBOT_SPEAK_PAD_S = 0.35

# Reactions. The robot perks up when a challenge opens and nods or droops on
# the verdict. Turn off if the movement distracts more than it adds.
ROBOT_EMOTES = True

# ---------------------------------------------------------------------------
# Camera presence tracking (optional, needs USE_ROBOT)
#
# Presence only: the robot looks at whoever it can see. It scores NOTHING. No
# verb, pack or answer depends on the camera, so a tracking failure costs you
# an inattentive robot and nothing else.
# ---------------------------------------------------------------------------
USE_TRACKER = False

TRACKER_FPS          = 8.0    # camera polls per second
TRACKER_LOOK_S       = 0.7    # how long each head move takes
TRACKER_DEADZONE_PX  = 60     # ignore targets already this near the centre
TRACKER_MIN_FACE_PX  = 48     # smallest face to believe, rejects background noise
TRACKER_LOST_S       = 4.0    # nobody seen this long -> return to neutral
TRACKER_RECENTRE_S   = 12.0   # and idly look around every this often

# The camera is mounted IN the head, so tracking moves the view it is tracking
# from. Waiting this long after a move before trusting the next frame stops the
# robot chasing its own motion.
TRACKER_SETTLE_S = 0.35

# ---------------------------------------------------------------------------
# Gamemaster web console (this screen faces AWAY from the children)
# ---------------------------------------------------------------------------
HOST = '0.0.0.0'
PORT = 5000
