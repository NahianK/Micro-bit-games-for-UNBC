# mb_transmitter.py — Flash onto the TRANSMITTER micro:bit
#
# ── WHAT THIS DOES ───────────────────────────────────────────────────────────
# This is a minimal standalone proximity transmitter.
# It broadcasts "PING" every ~200ms so any nearby receiver can detect it.
#
# Flash this onto ONE micro:bit and carry it around.
# Flash mb_receiver.py onto one or more OTHER micro:bits.
# The receiver LEDs fill up as you bring this micro:bit closer.
#
# ── HARDWARE ─────────────────────────────────────────────────────────────────
#   - 1 × micro:bit (any version) with battery pack or USB
#   - No cables needed after flashing
#
# ── FLASHING ─────────────────────────────────────────────────────────────────
#   1. Go to https://python.microbit.org/v/3
#   2. Paste this entire file into the editor
#   3. Click Send to micro:bit
#   4. The LED matrix shows a right-pointing arrow (→) to indicate TX mode
#
# ── CALIBRATION ──────────────────────────────────────────────────────────────
#   RADIO_POWER controls the signal range.
#   Lower value = shorter range (better for indoor proximity games).
#   Higher value = longer range (better for outdoor use).
#
#   Suggested values:
#     RADIO_POWER = 1  →  max range ~1–2m   (tight proximity, passing a ball)
#     RADIO_POWER = 3  →  max range ~3–5m   (default, good for most games)
#     RADIO_POWER = 7  →  max range ~10–15m (outdoor, large spaces)
#
#   Match RADIO_POWER here with the RSSI thresholds in mb_receiver.py.
# ─────────────────────────────────────────────────────────────────────────────

from microbit import *
import radio
import random

# ── SETTINGS — adjust to suit your environment ───────────────────────────────
RADIO_GROUP   = 42      # must match mb_receiver.py
RADIO_POWER   = 3       # 0–7; lower = shorter range  ← CALIBRATE THIS
BROADCAST_MS  = 200     # how often to send (ms); lower = more responsive
JITTER_MS     = 40      # random extra delay to reduce packet collisions
#                         (important when multiple transmitters are active)
# ─────────────────────────────────────────────────────────────────────────────

radio.on()
radio.config(group=RADIO_GROUP, power=RADIO_POWER)

display.show(Image.ARROW_E)   # → arrow means "I am the transmitter"

last_tx = 0

while True:
    now = running_time()
    if now - last_tx >= BROADCAST_MS + random.randint(0, JITTER_MS):
        radio.send("PING")
        last_tx = now
    sleep(10)
