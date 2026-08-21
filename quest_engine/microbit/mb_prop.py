# mb_prop.py - Quest Engine prop beacon. OPTIONAL.
#
# Flash this onto a micro:bit that gets hidden in the play area (the dragon's
# egg, the black-box beacon). It only exists to support the NEAR verb, where
# children hunt for it by watching their wand's LEDs fill up.
#
# With six boards you cannot have this AND five players: the split is
#   1 bridge + 5 wands            (no prop, no NEAR challenges)
#   1 bridge + 4 wands + 1 prop   (NEAR challenges available)
#
# All it does is shout "B|<id>" a few times a second. The wands measure the
# signal strength of that shout and turn it into a proximity display.
#
# REUSE: this is treasure_hunt/microbit/mb_treasure.py stripped down to the
# beacon behaviour, with the message renamed to match this game's wire format.
#
# RADIO_POWER is deliberately LOW. At full power everything in a school hall
# reads as "very close" and the hunt is over before it starts.
#
# Requires micro:bit V2 hardware for consistency with the rest of the game,
# though this file alone would run on a V1.

from microbit import *
import radio
import random

RADIO_GROUP = 42
RADIO_POWER = 3          # low on purpose, so distance actually differentiates

PROP_ID = 'P1'           # change per prop if you ever run more than one

BROADCAST_MS     = 300
BROADCAST_JITTER = 80    # stagger sends so props do not collide with wands
LOOP_SLEEP_MS    = 10
ID_WINDOW_MS     = 5000


def assign_id():
    """
    Button B steps the prop number 1-5, Button A confirms early.
    Mirrors the treasure id pattern from treasure_hunt so the muscle memory
    carries over: B sets, A confirms.
    """
    display.scroll('P?', delay=60, wait=False)
    num = 0
    deadline = running_time() + ID_WINDOW_MS
    while running_time() < deadline:
        if button_b.was_pressed():
            num += 1
            if num > 5:
                num = 1
            display.show(str(num))
        if button_a.was_pressed():
            break
        sleep(50)
    return 'P{}'.format(num if num > 0 else 1)


PROP_ID = assign_id()

radio.config(group=RADIO_GROUP, power=RADIO_POWER, queue=8, length=64)
radio.on()

display.scroll(PROP_ID, delay=80)

# A single dim pixel: bright enough to find in a cupboard when you are packing
# up, dim enough not to give the hiding place away.
display.show(Image('00000:00000:00300:00000:00000'))

next_broadcast = 0

while True:
    now = running_time()
    if now >= next_broadcast:
        radio.send('B|{}'.format(PROP_ID))
        next_broadcast = now + BROADCAST_MS + random.randint(0, BROADCAST_JITTER)
    sleep(LOOP_SLEEP_MS)
