# mb_ball.py — Flash onto Micro:bit 1 (inside the ball)
#
# This micro:bit lives in/on the physical ball.
# It broadcasts "BALL" every ~200ms so players can measure proximity.
# When it receives a HOLDER:<id> message it shows the holder's number on the LED.
#
# No role selection needed — this device is always the ball.

from microbit import *
import radio
import random

# ── constants ────────────────────────────────────────────────────────────────
RADIO_GROUP       = 42
RADIO_POWER       = 3       # 0 (weakest) – 7 (strongest) — lower = better distance differentiation
BROADCAST_MS      = 200     # base broadcast interval
JITTER_MS         = 40      # random extra delay to reduce packet collisions

# ── setup ─────────────────────────────────────────────────────────────────────
radio.on()
radio.config(group=RADIO_GROUP, power=RADIO_POWER)
display.scroll("BALL", delay=80)
display.show(Image.DIAMOND)

last_broadcast = 0
holder = None

# ── main loop ─────────────────────────────────────────────────────────────────
while True:
    now = running_time()

    # Check for incoming HOLDER claim from a player
    # radio.receive() returns a plain string — no RSSI needed on the ball
    text = radio.receive()
    if text:
        if text.startswith("HOLDER:"):
            holder = text[7:]           # e.g. "1" or "2"
            display.show(str(holder))

    # Broadcast presence on schedule
    if now - last_broadcast >= BROADCAST_MS + random.randint(0, JITTER_MS):
        radio.send("BALL")
        last_broadcast = now

    sleep(10)
