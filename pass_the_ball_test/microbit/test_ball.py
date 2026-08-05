# test_ball.py — Flash onto the BALL micro:bit to verify it is broadcasting.
#
# Every 500ms it sends "PING" and toggles the centre LED so you can see
# it is alive and transmitting.  No button presses needed.

from microbit import *
import radio

RADIO_GROUP = 42
RADIO_POWER = 7

radio.on()
radio.config(group=RADIO_GROUP, power=RADIO_POWER)

display.scroll("TX", delay=80)

centre_on = False
last_tx = 0

while True:
    now = running_time()
    if now - last_tx >= 500:
        radio.send("PING")
        centre_on = not centre_on
        display.set_pixel(2, 2, 9 if centre_on else 0)   # centre pixel blinks
        last_tx = now
    sleep(20)
