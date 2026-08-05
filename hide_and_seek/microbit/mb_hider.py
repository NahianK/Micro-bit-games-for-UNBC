# mb_hider.py — Flash onto Hider micro:bits (full version — battery powered)
#
# ── REUSE NOTE ──────────────────────────────────────────────────────────────
# REUSE: identical to hide_and_seek_test/microbit/mb_hider.py EXCEPT the
# serial relay section is removed — the dedicated bridge micro:bit handles all
# relaying in the full version. Hiders do not need to be USB-connected.
# ────────────────────────────────────────────────────────────────────────────
#
# HIDER SETUP:
#   Flash this file onto each hider micro:bit (battery powered, no USB needed).
#   Press Button B once per hider number within the first 5 seconds:
#     1 press = H1, 2 presses = H2, 3 presses = H3 ...  Default: H1
#   Press Button A to confirm immediately.
#   The micro:bit will scroll "H1" (or H2 etc.), then show your number.
#   Then GO HIDE — it broadcasts HIDE:H<id> every ~300ms.
#
# CALIBRATION:
#   RSSI thresholds live in mb_seeker.py. Recalibrate each session —
#   the hiding spot and room geometry change every game.

from microbit import *
import radio
import random

# ── constants ────────────────────────────────────────────────────────────────
RADIO_GROUP  = 42
RADIO_POWER  = 7          # hiders broadcast at full power  ← CALIBRATE if needed
BROADCAST_MS = 300        # base broadcast interval (ms)
JITTER_MS    = 80         # random jitter — reduces packet collisions with multiple hiders
ID_WINDOW_MS = 5000       # ms to accept Button B presses for hider ID

# ── hider ID assignment ───────────────────────────────────────────────────────
# Press Button B once per hider number within first 5 seconds.
# Press Button A to confirm immediately. Default: H1.
display.scroll("ID?", delay=80)
hider_num = 0
deadline  = running_time() + ID_WINDOW_MS

while running_time() < deadline:
    if button_b.was_pressed():
        hider_num += 1
        if hider_num > 5:
            hider_num = 1
        display.show(str(hider_num))
    if button_a.was_pressed():
        break
    sleep(50)

if hider_num == 0:
    hider_num = 1

hider_id = "H{}".format(hider_num)   # e.g. "H1", "H2"
display.scroll(hider_id, delay=80)
display.show(str(hider_num))          # show number while hiding

# ── radio setup ───────────────────────────────────────────────────────────────
radio.on()
radio.config(group=RADIO_GROUP, power=RADIO_POWER)

last_broadcast = 0

# ── main loop ─────────────────────────────────────────────────────────────────
while True:
    now = running_time()

    # ── GAME-SPECIFIC: broadcast hider presence ───────────────────────────────
    # Format: "HIDE:H<id>" — seeker and bridge both recognise this prefix
    # REUSE: broadcast timing/jitter pattern is identical to pass the ball
    if now - last_broadcast >= BROADCAST_MS + random.randint(0, JITTER_MS):
        radio.send("HIDE:{}".format(hider_id))
        last_broadcast = now

    sleep(10)
