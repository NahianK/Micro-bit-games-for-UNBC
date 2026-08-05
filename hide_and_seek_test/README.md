# Hide and Seek — Test Version (3 micro:bits)

A proximity-based Hide and Seek game using BBC micro:bits and a browser dashboard.
This is the **test/development version** using 3 micro:bits. For the full version
with a dedicated bridge and up to 5 hiders, see `../hide_and_seek/`.

---

## Hardware

| Role | micro:bit | Connection |
|------|-----------|------------|
| Hider 1 (relay) | micro:bit v2 | **USB to PC** |
| Seeker | micro:bit v2 | Battery pack (free to move) |
| Hider 2 (optional) | micro:bit v2 | Battery pack |

The **relay hider** doubles as the USB serial bridge — it broadcasts its own
hiding signal AND relays all radio traffic it hears to the computer.

---

## Flashing Order

### 1. Flash the Hider (relay — USB)
- Open `microbit/mb_hider.py` in the micro:bit Python editor or use `uflash`
- Flash onto the micro:bit that will stay USB-connected

### 2. Flash the Seeker
- Open `microbit/mb_seeker.py`
- Flash onto the free-moving seeker micro:bit (use battery pack)

### 3. (Optional) Flash a second Hider
- Flash `microbit/mb_hider.py` onto a third micro:bit with a battery pack

---

## Hider ID Assignment (Button B)

During the **5-second boot window** after flashing (or reset):

1. Press **Button B** once per hider number
   - 1 press → H1
   - 2 presses → H2
   - 3 presses → H3
2. Press **Button A** to confirm immediately
3. If no button pressed, defaults to **H1**

The micro:bit scrolls the assigned ID (e.g. "H1") then shows the number on the LED.

> The relay hider should be assigned **H1** (1 press of Button B, or just wait).

---

## Running the Computer App

```powershell
cd "D:\Cursor Repositories\hide_and_seek_test\computer_app"
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000** in a browser.

Check `config.py` first:
- Set `SERIAL_PORT` to the correct COM port (check Device Manager → Ports)
- Recalibrate `RSSI_HOT`, `RSSI_WARM` before each session (see below)

---

## Gameplay

1. **Setup**: Flash all micro:bits, run `python app.py`, open the dashboard.
2. **Hide**: Hiders go to their hiding spots. The relay hider (H1) stays USB-connected.
3. **Seek**: Seeker walks around. The seeker's LED fills outward as they get closer to any hider.
   - 1 LED (centre dot) = far away
   - 25 LEDs (all on) = very close / "found" range
4. **Tag**: When all LEDs are on, the seeker presses **Button A** to tag the nearest hider.
   - The dashboard marks that hider's card as **FOUND** (green glow).
5. **Win**: Find all hiders!

---

## Dashboard

The dashboard at `http://localhost:5000` shows one card per detected hider:
- **Seeker proximity bar** — fills based on how close the seeker is
- **HOT / WARM / COLD** label
- **Time hiding** counter (counts up until tagged)
- **FOUND** badge appears when the seeker tags that hider

---

## Calibration (Required Each Session)

> **Hiding spots change every game — always recalibrate before playing.**

RSSI values depend on the hiding spot, room geometry, walls, and obstacles.

1. Place a hider at the intended hiding spot with the micro:bit powered on.
2. Run `python app.py` and watch the dashboard RSSI values.
3. Walk toward the hider from the seeker's starting position and note:
   - RSSI at "found" distance (arm's length) → set as `RSSI_HOT`
   - RSSI at "getting warmer" distance (~1–2m) → set as `RSSI_WARM`
   - RSSI at farthest position → set as `RSSI_FLOOR` in `mb_seeker.py`
4. Update values in:
   - `mb_seeker.py` → `RSSI_HOT`, `RSSI_WARM`, `RSSI_FLOOR`
   - `config.py` → `RSSI_HOT`, `RSSI_WARM`
5. Reflash `mb_seeker.py` onto the seeker micro:bit.

---

## Radio Protocol

| Message | Who broadcasts | Meaning |
|---------|----------------|---------|
| `HIDE:H1` | Hider | "I am hider H1, I'm hiding" |
| `SEEK:H1:-65` | Seeker | "I'm -65 dBm from hider H1" |
| `TAGGED:H1` | Seeker | "I found hider H1!" |

The relay hider prints everything it hears to USB serial:
```
HIDE:H2,-70        ← second hider seen by relay (rssi at relay)
SEEK:H1:-65,-58    ← seeker proximity to H1, relay's seeker signal
TAGGED:H1,-45      ← seeker tagged H1
```

---

## Full Version

The full version (`../hide_and_seek/`) uses a dedicated bridge micro:bit
(identical to Pass the Ball) so hiders don't need to be USB-connected.
Supports 1–5 hiders all on battery packs.
