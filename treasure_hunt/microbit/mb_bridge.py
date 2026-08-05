# mb_bridge.py — Flash onto the dedicated Bridge micro:bit (Micro:bit 1)
#
# ── REUSE NOTE ──────────────────────────────────────────────────────────────
# This file is IDENTICAL for all games (Pass the Ball, Hide and Seek,
# Treasure Hunt). The bridge is game-agnostic — it relays everything it hears
# over radio to the computer via USB serial. No changes needed between games.
# ────────────────────────────────────────────────────────────────────────────
#
# This device is STATIONARY — place it near the computer and keep the USB
# cable connected at all times. It is NOT a player.
#
# It listens to all radio traffic on group 42 and relays every packet to
# the computer as a single serial line: "<message>,<rssi>\n"
#
# Example serial output:
#   BALL,-72          → ball broadcast; rssi = ball's distance to bridge
#   P1:-65,-80        → player 1's ball RSSI (-65), player's rssi at bridge (-80)
#   P3:-55,-70        → player 3's ball RSSI (-55), player's rssi at bridge (-70)
#   HOLDER:2,-55      → player 2 claiming possession (used by ball LED)
#
# LED: downward arrow (toward USB) confirms bridge mode.
# Button A: scrolls the radio group on screen for debugging.

from microbit import *
import radio

RADIO_GROUP = 42
RADIO_POWER = 7         # bridge listens at max power to hear all players

radio.on()
radio.config(group=RADIO_GROUP, power=RADIO_POWER)

display.scroll("BRDG", delay=80)
display.show(Image.ARROW_S)   # pointing down = USB connected below

while True:
    packet = radio.receive_full()
    if packet:
        raw, rssi, _ = packet

        # MicroPython v2 returns bytes with a 3-byte radio header — strip & decode
        # REUSE: this decoding block is identical in all bridge/relay firmware
        if isinstance(raw, bytes):
            text = "".join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
        else:
            text = str(raw).strip()

        if text:
            print("{},{}".format(text, rssi))

    # Button A: show radio group on screen for debugging
    if button_a.was_pressed():
        display.scroll("GRP" + str(RADIO_GROUP), delay=80)
        display.show(Image.ARROW_S)

    sleep(5)
