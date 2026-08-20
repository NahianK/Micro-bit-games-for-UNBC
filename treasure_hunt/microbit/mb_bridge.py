# mb_bridge.py — Treasure Hunt bridge micro:bit (USB relay + registration downlink)
#
# REUSE NOTE: The uplink (radio → serial) section is identical to all other
# games in this repo. A downlink section has been added to relay registration
# commands from the PC to the radio group.
#
# This device is STATIONARY — keep the USB cable connected at all times.
# It is NOT a hunter or a treasure.
#
# UPLINK (radio → PC serial, every packet):
#   <message>,<rssi>\n        — anything heard on radio group 42
#
# DOWNLINK (PC serial → radio, only RG| registration commands):
#   RG|S|<tok>\n              — broadcast REG_START to all hunters
#   RG|A|<nonce>|<tok>|<code>\n   — assign code to one hunter
#   RG|K|<nonce>|<hid>\n     — confirm binding
#   RG|E\n                   — end / cancel session
#   RG|G\n                   — game start (hunters play go-jingle)
#
# The bridge relays ALL radio packets upward and only validated RG| commands
# downward. It never calls uart.init() — that would break the USB serial link.
#
# LED: down arrow (towards USB) = bridge mode.
# Button A: scroll radio group for debugging.

from microbit import *
import radio

RADIO_GROUP = 42
RADIO_POWER = 7   # max power so the bridge hears all devices

radio.config(group=RADIO_GROUP, power=RADIO_POWER, queue=8, length=64)
radio.on()

display.scroll('BRDG', delay=80)
display.show(Image.ARROW_S)   # arrow pointing down = USB connected below

rx_buffer = b''   # partial serial line arriving from the PC


def decode(raw):
    """Strip the 3-byte radio header and return printable ASCII."""
    if isinstance(raw, bytes):
        return ''.join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
    return str(raw).strip()


while True:
    # -----------------------------------------------------------------------
    # DOWNLINK: commands pushed from the PC to broadcast over radio
    # -----------------------------------------------------------------------
    # uart.any() is true when bytes are waiting in the USB serial buffer.
    # Do NOT call uart.init() here — the default UART IS the USB connection
    # that print() writes to; reinitialising it breaks both directions.
    if uart.any():
        chunk = uart.read()
        if chunk:
            rx_buffer += chunk
            while b'\n' in rx_buffer:
                line, rx_buffer = rx_buffer.split(b'\n', 1)
                try:
                    cmd = line.decode('utf-8').strip()
                    # Only relay validated registration commands to the radio.
                    # Anything else is silently discarded (no error propagation).
                    if cmd.startswith('RG|') and len(cmd) <= 60:
                        radio.send(cmd)
                except Exception:
                    pass  # never let a bad byte take the bridge down
            # Safety valve: if no newline arrives within 200 bytes, discard.
            if len(rx_buffer) > 200:
                rx_buffer = b''

    # -----------------------------------------------------------------------
    # UPLINK: every radio packet forwarded to the PC
    # -----------------------------------------------------------------------
    packet = radio.receive_full()
    if packet:
        raw, rssi, _ = packet
        text = decode(raw)
        if text:
            print('{},{}'.format(text, rssi))

    # Debug: Button A scrolls the radio group
    if button_a.was_pressed():
        display.scroll('GRP{}'.format(RADIO_GROUP), delay=80)
        display.show(Image.ARROW_S)

    sleep(5)
