# mb_ball.py — Flash onto the Ball micro:bit (Micro:bit 2)
#
# ── REUSE NOTE ──────────────────────────────────────────────────────────────
# This file is reusable for Treasure Hunt (the treasure broadcasts presence
# the same way the ball does). For Hide and Seek, each hider gets a copy of
# this file — the broadcast message can be changed from "BALL" to "HIDE:<id>"
# to let the seeker identify each hider separately.
# ────────────────────────────────────────────────────────────────────────────
#
# Lives inside/on the physical ball. Broadcasts "BALL" every ~200ms.
# When it receives "HOLDER:<id>" from a player it shows that player's number.
# Micro:bit 1 is the dedicated bridge (USB to computer) — not this device.

from microbit import *
import radio
import random

# ── constants ────────────────────────────────────────────────────────────────
RADIO_GROUP  = 42
RADIO_POWER  = 3        # Lower power = better distance differentiation
                        # ← CALIBRATE: raise if signal drops out too quickly,
                        #              lower if all players always read HOT
BROADCAST_MS = 200      # base broadcast interval (ms)
JITTER_MS    = 40       # random extra delay to reduce packet collisions

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
    # radio.receive() returns a plain string — simpler and more compatible than receive_full()
    # REUSE: for other games change "HOLDER:" to the appropriate claim message
    text = radio.receive()
    if text:
        if text.startswith("HOLDER:"):
            holder = text[7:]           # e.g. "1" or "4"
            display.show(str(holder))

    # Broadcast presence on schedule
    # GAME-SPECIFIC: change "BALL" to "TREASURE" or "HIDE:<id>" for other games
    if now - last_broadcast >= BROADCAST_MS + random.randint(0, JITTER_MS):
        radio.send("BALL")
        last_broadcast = now

    sleep(10)
