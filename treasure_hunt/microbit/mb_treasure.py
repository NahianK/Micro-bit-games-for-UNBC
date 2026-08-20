# mb_treasure.py - Treasure Hunt FULL version
# Flash onto treasure micro:bits (battery powered in field).
# REUSE: identical to treasure_hunt_test\microbit\mb_treasure.py MINUS the serial relay section.
# In the full version a dedicated bridge micro:bit (mb_bridge.py) handles USB serial relay.
# Note: RADIO_POWER=3 (lower power = better proximity ranging; bridge can differentiate proximity).

import radio
import microbit
from microbit import display, button_a, button_b, Image, sleep, running_time
import random

# ---------------------------------------------------------------------------
# Calibration constants (recalibrate each session with actual hardware)
# ---------------------------------------------------------------------------
RSSI_HOT   = -50   # very close / found  <- CALIBRATE THIS each session
RSSI_WARM  = -65   # getting warmer       <- CALIBRATE THIS each session
RSSI_FLOOR = -80   # max useful range     <- CALIBRATE THIS each session

RADIO_GROUP = 42
RADIO_POWER = 3    # lower power = better proximity range (see note above)

BROADCAST_INTERVAL = 300   # ms between TRS broadcasts
BROADCAST_JITTER   = 80    # ±ms jitter
CLAIM_WINDOW_MS    = 10000 # max ms between CLAIM and B-press on treasure

# ---------------------------------------------------------------------------
# ID assignment via Button B presses during 5-second boot window
# Button A confirms immediately (or wait 5 s for default T1)
# ---------------------------------------------------------------------------
def assign_id():
    display.scroll('T?', delay=60, wait=False)
    press_count = 0
    deadline = running_time() + 5000
    while running_time() < deadline:
        if button_b.was_pressed():
            press_count += 1
            display.show(str(press_count))
        if button_a.was_pressed():
            break
    treasure_id = max(1, min(5, press_count)) if press_count > 0 else 1
    return 'T{}'.format(treasure_id)

TREASURE_ID = assign_id()

# Show treasure chest icon then ID
display.show(Image.DIAMOND)
sleep(600)
display.scroll(TREASURE_ID, delay=80)

# ---------------------------------------------------------------------------
# Radio setup
# ---------------------------------------------------------------------------
radio.config(group=RADIO_GROUP, power=RADIO_POWER, queue=8, length=64)
radio.on()

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
last_claim         = None   # hunter_id of most recent CLAIM received
last_claim_time_ms = 0      # running_time() when claim arrived
next_broadcast_ms  = 0      # schedule next TRS broadcast
is_found           = False  # stop TRS beacons after a confirmed find

# ---------------------------------------------------------------------------
# Helper: MicroPython v2 bytes decoding (REQUIRED for receive_full)
# ---------------------------------------------------------------------------
def decode_packet(packet):
    """Return (text, rssi) or (None, None) if packet is invalid."""
    if packet is None:
        return None, None
    raw, rssi_val, _ = packet
    if isinstance(raw, bytes):
        text = "".join(chr(b) for b in raw[3:] if 32 <= b < 127).strip()
    else:
        text = str(raw).strip()
    return text, rssi_val

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
while True:
    now = running_time()

    # --- Broadcast TRS beacon (silent once found so hunters stop ranging) ---
    if now >= next_broadcast_ms:
        if not is_found:
            radio.send('TRS:{}'.format(TREASURE_ID))
        next_broadcast_ms = now + BROADCAST_INTERVAL + random.randint(-BROADCAST_JITTER, BROADCAST_JITTER)

    # --- Receive radio packets ---
    packet = radio.receive_full()
    text, rssi_val = decode_packet(packet)

    if text:
        # NOTE: In full version there is NO serial relay here.
        # The dedicated bridge micro:bit (mb_bridge.py) handles all serial forwarding.

        # Track incoming CLAIM packets
        if text.startswith('CLAIM:'):
            # Format: CLAIM:H<id>
            parts = text.split(':')
            if len(parts) == 2:
                last_claim = parts[1]          # e.g. 'H1'
                last_claim_time_ms = running_time()

    # --- FOUND mechanic: Button B on treasure confirms find ---
    if button_b.was_pressed():
        if (last_claim is not None and
                (running_time() - last_claim_time_ms) <= CLAIM_WINDOW_MS):
            found_msg = 'FOUND:{}:{}'.format(TREASURE_ID, last_claim)
            is_found = True
            # Repeat so nearby hunters (not just the finder) hear it
            for _ in range(4):
                radio.send(found_msg)
                sleep(80)
            display.show(Image.YES)
            last_claim = None
            last_claim_time_ms = 0
        else:
            # No recent claim or window expired - flash to indicate nothing to confirm
            display.show(Image.NO)
            sleep(500)
            display.show(TREASURE_ID[1])  # show numeric part
