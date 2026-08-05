# Hide and Seek — Full Version (Bridge + Seeker + 1–5 Hiders)

A proximity-based Hide and Seek game using BBC micro:bits and a browser dashboard.
This is the **full version** using a dedicated bridge micro:bit.
For the simpler 3-micro:bit test setup, see `../hide_and_seek_test/`.

---

## Hardware

| Role | micro:bit | Connection |
|------|-----------|------------|
| Bridge | micro:bit v2 | **USB to PC / Raspberry Pi** |
| Seeker | micro:bit v2 | Battery pack (free to move) |
| Hider 1–5 | micro:bit v2 (×1–5) | Battery pack each |

The **bridge** is stationary and game-agnostic — it relays all radio traffic to the
computer via USB serial. It is the same firmware as Pass the Ball (`mb_bridge.py`).
Hiders are fully wireless on battery packs.

---

## Flashing Order

### 1. Flash the Bridge (USB — stays plugged in)
- Flash `microbit/mb_bridge.py` (identical to pass_the_ball bridge)
- LED shows a downward arrow (↓) to confirm bridge mode

### 2. Flash each Hider
- Flash `microbit/mb_hider.py` onto each hider micro:bit
- Assign IDs at boot (see below)

### 3. Flash the Seeker
- Flash `microbit/mb_seeker.py` onto the seeker micro:bit
- No ID assignment needed — there is only one seeker

---

## Hider ID Assignment (Button B)

During the **5-second boot window** after flashing (or reset):

1. Press **Button B** once per hider number:
   - 1 press → H1
   - 2 presses → H2
   - 3 presses → H3
   - 4 presses → H4
   - 5 presses → H5
2. Press **Button A** to confirm immediately
3. If no button pressed, defaults to **H1**

The micro:bit scrolls the assigned ID (e.g. "H2") then shows the number on the LED.
Each hider must have a unique number — flash and assign them one at a time.

---

## Running the Computer App

```powershell
cd "D:\Cursor Repositories\hide_and_seek\computer_app"
pip install -r requirements.txt
python app.py
```

On **Raspberry Pi**:
```bash
cd ~/hide_and_seek/computer_app
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000** (or `http://<pi-ip>:5000` from another device).

Check `config.py` first:
- **Windows**: Set `SERIAL_PORT` to the correct COM port (Device Manager → Ports)
- **Raspberry Pi**: Change to `SERIAL_PORT = '/dev/ttyACM0'`
- Recalibrate `RSSI_HOT`, `RSSI_WARM` before each session

---

## Gameplay

1. **Setup**: Flash all micro:bits. Bridge stays USB-connected. Run `python app.py`.
2. **Hide**: Hiders go to their spots. Dashboard shows cards as they appear.
3. **Seek**: Seeker walks around. The seeker's LED fills outward toward the nearest hider:
   - 1 LED (centre dot) = far away
   - 25 LEDs (all on) = very close / "found" range
4. **Tag**: Seeker presses **Button A** when all LEDs are on.
   - Dashboard marks that hider's card as **FOUND** (green glow + badge).
5. **Win**: Find all hiders!

---

## Dashboard

The dashboard at `http://localhost:5000` shows one card per detected hider:
- **Seeker proximity bar** — fills based on how close the seeker is (from SEEK packets)
- **HOT / WARM / COLD** label
- **Time hiding** counter (counts up until tagged, then freezes)
- **FOUND** badge appears when the seeker tags that hider
- **Bridge signal** (secondary) — hider's signal at the bridge

---

## Calibration (Required Each Session)

> **Hiding spots change every game — always recalibrate before playing.**

RSSI values depend on the hiding spot, room geometry, walls, and obstacles.

1. Place a hider at the intended hiding spot with the micro:bit powered on.
2. Run `python app.py` and watch the dashboard signal values.
3. Walk toward the hider from the seeker's starting position and note:
   - RSSI at "found" distance (arm's length) → set as `RSSI_HOT`
   - RSSI at "getting warmer" distance (~1–2m) → set as `RSSI_WARM`
   - RSSI at farthest position → set as `RSSI_FLOOR` in `mb_seeker.py`
4. Update values in:
   - `microbit/mb_seeker.py` → `RSSI_HOT`, `RSSI_WARM`, `RSSI_FLOOR`
   - `computer_app/config.py` → `RSSI_HOT`, `RSSI_WARM`
5. Reflash `mb_seeker.py` onto the seeker micro:bit.

---

## Radio Protocol

| Message | Who broadcasts | Meaning |
|---------|----------------|---------|
| `HIDE:H1` | Hider H1 | "I am hider H1, I'm hiding" |
| `SEEK:H1:-65` | Seeker | "I'm -65 dBm from hider H1" |
| `TAGGED:H1` | Seeker | "I found hider H1!" |

The bridge prints everything it hears to USB serial:
```
HIDE:H1,-72        ← hider H1 seen at bridge (rssi at bridge)
HIDE:H2,-68        ← hider H2 seen at bridge
SEEK:H1:-65,-58    ← seeker's RSSI from H1 (-65), seeker's signal at bridge (-58)
SEEK:H2:-55,-60    ← seeker's RSSI from H2 (-55), seeker's signal at bridge (-60)
TAGGED:H1,-45      ← seeker tagged H1
```

---

## Code Reuse Table

| File | Identical to test version? | Identical to pass_the_ball? |
|------|----------------------------|-----------------------------|
| `microbit/mb_bridge.py` | ✅ Yes | ✅ Yes (unchanged) |
| `microbit/mb_seeker.py` | ✅ Yes | Partial (PIXEL_ORDER, proximity_image, bytes decode reused) |
| `microbit/mb_hider.py` | ✅ Yes (relay block removed) | Partial (broadcast pattern reused) |
| `computer_app/app.py` | ✅ Yes | Structure reused, GameState different |
| `computer_app/serial_reader.py` | ✅ Yes | Structure reused, _parse() different |
| `computer_app/config.py` | ✅ Yes (SERIAL_PORT Pi note added) | Structure reused |
| `computer_app/static/dashboard.js` | ✅ Yes | rssiPercent() reused |
| `computer_app/templates/index.html` | Title/empty state differ | CSS/style identical |
| `computer_app/requirements.txt` | ✅ Yes | ✅ Yes |

---

## Test Version

For a quick 3-micro:bit test with one hider doubling as the USB relay,
see `../hide_and_seek_test/`. No dedicated bridge needed.
