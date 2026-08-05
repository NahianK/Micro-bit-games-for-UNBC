# mb_player.py — Flash onto Player micro:bits (up to 5 players)
#
# ── REUSE NOTE ──────────────────────────────────────────────────────────────
# This file is IDENTICAL in structure to pass_the_ball_test/microbit/mb_player.py
# with one key difference: serial print is REMOVED (bridge handles all relaying).
# The proximity_image(), smooth(), PIXEL_ORDER, and radio setup blocks can be
# copied directly into hide_and_seek and treasure_hunt player firmware.
# Only the GAMEPLAY section (possession claim logic) is game-specific.
# ────────────────────────────────────────────────────────────────────────────
#
# PLAYER ID ASSIGNMENT AT BOOT:
#   Press Button A once per player number within the first 5 seconds.
#   Example: 1 press = Player 1, 4 presses = Player 4, 5 presses = Player 5.
#   Press Button B at any time to confirm immediately.
#   LED shows your assigned number during selection.
#   Supports 2–5 players (just flash this same file on each player micro:bit).
#
# GAMEPLAY:
#   LED fills outward from the centre showing ball proximity:
#     1 dot  (centre only)  = ball is very far away
#     25 dots (all LEDs on) = ball is right here — possession range
#   Press Button A when all LEDs are fully lit to claim the ball.
#   The ball micro:bit will display your number.
#   Ball is automatically released when it moves away (throw detection).
#
# NOTE: Micro:bit 1 is the dedicated bridge (USB to computer).
#       Players do NOT need to be plugged in — all relaying is handled by the bridge.

from microbit import *
import radio
import random

# ── constants ────────────────────────────────────────────────────────────────
RADIO_GROUP   = 42
RADIO_POWER   = 7         # players broadcast at full power so bridge hears them

# ── CALIBRATION — update these after open-space recalibration ────────────────
#
#   RSSI_HOT  = signal strength at closest range (25 LEDs — possession zone)
#               Measure: hold ball touching/0–0.5m from player, read RSSI average
#               Current: -50 dBm ≈ touching to 0.5m (indoor calibration Aug 2026)
#
#   RSSI_FLOOR = signal strength at maximum useful range (1 LED)
#                Measure: hold ball at your max game distance, read RSSI average
#                Current: -80 dBm ≈ 5m (indoor calibration Aug 2026)
#                Note: recalibrate outdoors for reliable distance beyond 1m.
#
#   RSSI_WARM = possession release threshold — set roughly halfway between HOT and FLOOR
#               Current: -65 dBm ≈ 1–2m
#
#   LED count formula (linear, do not modify):
#       ratio = (rssi - RSSI_FLOOR) / (RSSI_HOT - RSSI_FLOOR)   # 0.0 to 1.0
#       count = 1 + int(ratio * 24)                               # 1 to 25 LEDs
#
RSSI_HOT      = -50       # dBm — 25 LEDs (~0–0.5m)  ← CALIBRATE THIS
RSSI_WARM     = -65       # dBm — possession release  ← CALIBRATE THIS
RSSI_FLOOR    = -80       # dBm — 1 LED  (~5m max)    ← CALIBRATE THIS
# ─────────────────────────────────────────────────────────────────────────────

SMOOTH_WINDOW = 5         # RSSI readings to average (higher = smoother but slower)
BROADCAST_MS  = 250       # base player broadcast interval (ms)
JITTER_MS     = 50        # random jitter to reduce packet collisions
ID_WINDOW_MS  = 5000      # ms to accept Button A presses for player ID

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
# REUSE: smooth() and PIXEL_ORDER and proximity_image() are identical across all games.

def smooth(history, new_val):
    history.append(new_val)
    if len(history) > SMOOTH_WINDOW:
        history.pop(0)
    return sum(history) // len(history)

# Pixel positions ordered from centre outward — determines LED fill pattern.
PIXEL_ORDER = [
    (2, 2),
    (2, 1), (2, 3), (1, 2), (3, 2),
    (1, 1), (3, 1), (1, 3), (3, 3),
    (2, 0), (2, 4), (0, 2), (4, 2),
    (1, 0), (3, 0), (0, 1), (4, 1),
    (0, 3), (4, 3), (1, 4), (3, 4),
    (0, 0), (4, 0), (0, 4), (4, 4),
]

def proximity_image(rssi):
    """
    Map RSSI to a 5x5 LED image that fills outward from the centre.
    RSSI_FLOOR → 1 LED  (centre dot only — ball at max range or beyond)
    RSSI_HOT   → 25 LEDs (all on — ball very close, possession range)
    LEDs increase linearly. Values outside range are clamped.

    To adjust the distance-to-LED mapping:
      - Change RSSI_HOT   to the RSSI you read at your desired closest range
      - Change RSSI_FLOOR to the RSSI you read at your desired furthest range
      - RSSI_WARM controls when held possession is released
    """
    # ── LED count calculation — do not modify this formula ───────────────────
    ratio = (rssi - RSSI_FLOOR) / (RSSI_HOT - RSSI_FLOOR)  # 0.0=far, 1.0=close
    ratio = max(0.0, min(1.0, ratio))
    count = 1 + int(ratio * 24)   # 1 to 25

    grid = [[0] * 5 for _ in range(5)]
    for i in range(count):
        col, row = PIXEL_ORDER[i]
        grid[row][col] = 9
    rows = ["".join(str(grid[r][c]) for c in range(5)) for r in range(5)]
    return Image(":".join(rows))

# ── state ─────────────────────────────────────────────────────────────────────
rssi_history   = []
ball_rssi      = -100
holding        = False
last_broadcast = 0

display.show(proximity_image(ball_rssi))   # start: 1 centre dot (no signal)

# ── main loop ─────────────────────────────────────────────────────────────────
while True:
    now = running_time()

    # ── receive any incoming packet ───────────────────────────────────────────
    packet = radio.receive_full()
    if packet:
        raw, rssi_val, _ = packet

        # MicroPython v2 returns bytes with a 3-byte radio header — strip & decode
        # REUSE: this decoding block is identical in all games using receive_full()
        if isinstance(raw, bytes):
            text = "".join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
        else:
            text = str(raw).strip()

        # ── GAME-SPECIFIC: react to ball broadcasts ───────────────────────────
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
            display.show(proximity_image(ball_rssi))

    # ── claim possession: must be close and press Button A ────────────────────
    # GAME-SPECIFIC: remove/replace this block for hide and seek / treasure hunt
    if not holding and ball_rssi > RSSI_HOT and button_a.was_pressed():
        holding = True
        radio.send("HOLDER:{}".format(player_id))
        display.show(proximity_image(ball_rssi))

    # ── broadcast own proximity data to bridge ────────────────────────────────
    # REUSE: this broadcast block is identical across all games
    if now - last_broadcast >= BROADCAST_MS + random.randint(0, JITTER_MS):
        radio.send("P{}:{}".format(player_id, ball_rssi))
        last_broadcast = now

    sleep(10)
