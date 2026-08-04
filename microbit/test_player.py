# test_player.py — Flash onto the USB-connected PLAYER micro:bit to verify
# serial output and radio reception both work.
#
# Every 1 second it prints "ALIVE" to serial so you know the serial link works.
# Any radio packet received is also printed immediately.
# LED shows a dot count of how many packets have been received (wraps at 25).

from microbit import *
import radio

RADIO_GROUP = 42
RADIO_POWER = 7

radio.on()
radio.config(group=RADIO_GROUP, power=RADIO_POWER)

display.scroll("RX", delay=80)
display.clear()

received = 0
last_alive = 0

while True:
    now = running_time()

    # Print heartbeat every 1 s so we know serial is working
    if now - last_alive >= 1000:
        print("ALIVE,t={}".format(now))
        last_alive = now

    # Print any received packet immediately
    packet = radio.receive_full()
    if packet:
        text, rssi, _ = packet
        received += 1
        print("PKT,{},{},n={}".format(text, rssi, received))
        # Show received count on LED (1-25)
        count = min(received, 25)
        display.show(Image('90000:' * 5) if count >= 25 else str(count % 10))

    sleep(10)
