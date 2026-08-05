# mb_player.py — Flash onto Micro:bit 2 (Player 1) and Micro:bit 3 (Player 2)
#
# PLAYER ID ASSIGNMENT AT BOOT:
#   Press Button A once per player number within the first 5 seconds.
#   Example: 1 press = Player 1, 2 presses = Player 2.
#   Button B at any time confirms and starts immediately.
#   LED counts down and shows your assigned number.
#
# GAMEPLAY:
#   LED fill shows how close the ball is — continuously:
#     1 dot  (top-left only) = ball is very far away
#     25 dots (all LEDs on)  = ball is right here — possession range
#   Press Button A when all LEDs are on to claim the ball.
#   The ball micro:bit will display your number.
#   Ball is automatically released when it moves away.
#
# SERIAL RELAY (Player 2 only — Micro:bit 3 plugged into computer via USB):
#   Every received radio packet is printed to serial automatically.
#   The computer app reads this stream to track proximity and possession.
#   No extra configuration needed — being plugged in via USB is enough.

from microbit import *
import radio
import random

# ── constants ────────────────────────────────────────────────────────────────
RADIO_GROUP     = 42
RADIO_POWER     = 7

# ── CALIBRATION — update these two values after open-space recalibration ──────
#
#   RSSI_HOT  = signal strength at the CLOSEST range (25 LEDs — possession zone)
#               Measure: hold ball touching/0–0.5m from player, read RSSI average
#               Current: -50 dBm ≈ touching to 0.5m (indoor calibration Aug 2026)
#
#   RSSI_FLOOR = signal strength at MAXIMUM useful range (1 LED)
#                Measure: hold ball at your max game distance, read RSSI average
#                Current: -68 dBm ≈ 6m (indoor calibration Aug 2026)
#                Note: indoor wall reflections cause non-linear readings beyond 1m.
#                      Recalibrate outdoors or in large open space for best results.
#
#   LED count formula (linear):
#       ratio = (rssi - RSSI_FLOOR) / (RSSI_HOT - RSSI_FLOOR)   # 0.0 to 1.0
#       count = 1 + int(ratio * 24)                               # 1 to 25 LEDs
#
#   RSSI_WARM = release threshold — player loses possession when ball moves beyond this
#               Set roughly halfway between RSSI_HOT and RSSI_FLOOR
#               Current: -65 dBm ≈ 1–2m
#
RSSI_HOT        = -50       # dBm — 25 LEDs (0–0.5m) ← CALIBRATE THIS
RSSI_WARM       = -65       # dBm — possession release point   ← CALIBRATE THIS
RSSI_FLOOR      = -80       # dBm — 1 LED  (~5-6m max range)   ← CALIBRATE THIS
# ─────────────────────────────────────────────────────────────────────────────

SMOOTH_WINDOW   = 5         # number of readings to average (higher = smoother but slower)
BROADCAST_MS    = 250       # base player broadcast interval (ms)
JITTER_MS       = 50        # random jitter added to reduce packet collisions
ID_WINDOW_MS    = 5000      # milliseconds to accept button presses for ID

# ── player ID assignment ──────────────────────────────────────────────────────
display.scroll("ID?", delay=80)
player_id = 0
deadline = running_time() + ID_WINDOW_MS

while running_time() < deadline:
    if button_a.was_pressed():
        player_id += 1
        if player_id > 5:
            player_id = 1
        display.show(str(player_id))
    if button_b.was_pressed():
        break
    sleep(50)

if player_id == 0:
    player_id = 1

display.scroll("P" + str(player_id), delay=80)

# ── radio setup ───────────────────────────────────────────────────────────────
radio.on()
radio.config(group=RADIO_GROUP, power=RADIO_POWER)

# ── helpers ───────────────────────────────────────────────────────────────────
def smooth(history, new_val):
    history.append(new_val)
    if len(history) > SMOOTH_WINDOW:
        history.pop(0)
    return sum(history) // len(history)

# Pixel positions ordered by distance from centre (2,2), expanding outward.
# Groups: centre → cross → inner diagonals → cross far → outer ring → corners.
PIXEL_ORDER = [
    (2, 2),
    (2, 1), (2, 3), (1, 2), (3, 2),   # up/down before left/right
    (1, 1), (3, 1), (1, 3), (3, 3),   # inner diagonals
    (2, 0), (2, 4), (0, 2), (4, 2),   # top/bottom middle before left/right extreme
    (1, 0), (3, 0), (0, 1), (4, 1),
    (0, 3), (4, 3), (1, 4), (3, 4),
    (0, 0), (4, 0), (0, 4), (4, 4),
]

def proximity_image(rssi):
    """
    Map RSSI to a 5x5 LED image that fills outward from the centre.

    RSSI_FLOOR → 1 LED  (centre dot only — ball at max range or beyond)
    RSSI_HOT   → 25 LEDs (all on — ball very close, possession range)

    LEDs increase linearly between RSSI_FLOOR and RSSI_HOT.
    Values outside that range are clamped (no wrapping).

    To adjust the distance-to-LED mapping:
      - Change RSSI_HOT   to the RSSI you read at your desired closest range
      - Change RSSI_FLOOR to the RSSI you read at your desired furthest range
      - RSSI_WARM controls when held possession is released (set between the two)
    """
    # ── LED count calculation — do not modify this formula ───────────────────
    ratio = (rssi - RSSI_FLOOR) / (RSSI_HOT - RSSI_FLOOR)  # 0.0=far, 1.0=close
    ratio = max(0.0, min(1.0, ratio))
    count = 1 + int(ratio * 24)          # 1 to 25

    # Build a blank 5x5 grid then light the first `count` pixels
    grid = [[0] * 5 for _ in range(5)]
    for i in range(count):
        col, row = PIXEL_ORDER[i]
        grid[row][col] = 9

    rows = ["".join(str(grid[r][c]) for c in range(5)) for r in range(5)]
    return Image(":".join(rows))

# ── state ─────────────────────────────────────────────────────────────────────
rssi_history    = []
ball_rssi       = -100      # smoothed RSSI from ball, updated on each BALL packet
holding         = False
last_broadcast  = 0

display.show(proximity_image(ball_rssi))   # start with 1 dot (no signal yet)

# ── main loop ─────────────────────────────────────────────────────────────────
while True:
    now = running_time()

    # ── receive any incoming packet ───────────────────────────────────────────
    packet = radio.receive_full()
    if packet:
        raw, rssi_val, _ = packet

        # MicroPython v2 returns bytes with a 3-byte radio header — strip & decode
        if isinstance(raw, bytes):
            text = "".join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
        else:
            text = str(raw).strip()

        # Relay every packet to serial (active only when USB-connected as Player 2)
        # Format: "<message>,<rssi_at_this_device>"
        print("{},{}".format(text, rssi_val))

        if text == "BALL":
            ball_rssi = smooth(rssi_history, rssi_val)
            if not holding:
                display.show(proximity_image(ball_rssi))

    # ── holding state: check if ball moved away ───────────────────────────────
    if holding:
        if ball_rssi < RSSI_WARM:
            holding = False
            display.show(proximity_image(ball_rssi))
        else:
            display.show(proximity_image(ball_rssi))   # stays full while holding

    # ── claim possession: must be close and press Button A ────────────────────
    if not holding and ball_rssi > RSSI_HOT and button_a.was_pressed():
        holding = True
        radio.send("HOLDER:{}".format(player_id))
        display.show(proximity_image(ball_rssi))

    # ── broadcast own player data ─────────────────────────────────────────────
    # Format: "P<id>:<ball_rssi>" — computer extracts player's distance to ball
    if now - last_broadcast >= BROADCAST_MS + random.randint(0, JITTER_MS):
        radio.send("P{}:{}".format(player_id, ball_rssi))
        last_broadcast = now

    sleep(10)
