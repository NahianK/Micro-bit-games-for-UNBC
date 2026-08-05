# Micro:bit Proximity Games for UNBC

A collection of radio-proximity games for children built on BBC micro:bit.
Designed for easy handoff — every file is commented for the next developer.

---

## Repository Structure

```
📁 proximity_demo/          ← Start here — standalone proximity sensor demo
📁 pass_the_ball_test/      ← Pass the Ball (3 micro:bits, test version)
📁 pass_the_ball_test_5_players/ ← Pass the Ball (6 micro:bits, 2–5 players)
📁 hide_and_seek_test/      ← Hide and Seek (3 micro:bits, test version)
📁 hide_and_seek/           ← Hide and Seek (full version, 1–5 hiders)
📁 treasure_hunt_test/      ← Treasure Hunt (3 micro:bits, test version)
📁 treasure_hunt/           ← Treasure Hunt (full version, 1–5 treasures)
```

Each folder contains:
- `microbit/` — MicroPython firmware files (flash onto micro:bits)
- `computer_app/` — Flask web dashboard (run on PC or Raspberry Pi B+)
- `README.md` — Game-specific setup and instructions

---

## How It All Works

All three games use the same core technology:

| Component | What it does |
|---|---|
| **Radio (2.4 GHz)** | micro:bits talk to each other wirelessly |
| **RSSI** | Signal strength → distance estimate |
| **USB Serial** | One micro:bit relays radio data to the computer |
| **Flask Dashboard** | Web app shows live proximity data on any browser |

### Proximity → LED display
Every micro:bit player/seeker/hunter shows the same LED pattern:

```
1 dot  = far away
● ○ ○ ○ ○
○ ○ ○ ○ ○     ~12 dots = medium distance
○ ○ ○ ○ ○
○ ○ ○ ○ ○
○ ○ ○ ○ ○

25 dots = very close / possession range
● ● ● ● ●
● ● ● ● ●
● ● ● ● ●
● ● ● ● ●
● ● ● ● ●
```

LEDs fill from the centre outward as the target gets closer.

---

## Quick Start — Proximity Demo

**Want to test the hardware before setting up a full game?**

Flash two micro:bits with the standalone demo in `proximity_demo/`:

| File | Flash onto |
|---|---|
| `mb_transmitter.py` | 1 micro:bit (the moving one) |
| `mb_receiver.py` | 1 or more micro:bits (the detectors) |

1. Go to [python.microbit.org/v/3](https://python.microbit.org/v/3)
2. Paste the file content → click **Send to micro:bit**
3. Move the transmitter toward a receiver — watch LEDs fill up
4. All 25 LEDs = transmitter is right next to that receiver

No computer app needed. Great for initial calibration.

---

## Games

### 🏈 Pass the Ball

One micro:bit lives inside/on the ball. Players carry micro:bits and see how
close the ball is. Press Button A when all LEDs light up to claim possession.

| Version | Micro:bits | Players |
|---|---|---|
| `pass_the_ball_test/` | 3 | 1 player + 1 USB relay |
| `pass_the_ball_test_5_players/` | 6 | 2–5 players + 1 dedicated bridge |

**Reusable code:** `PIXEL_ORDER`, `proximity_image()`, `smooth()`, bytes decoding,
radio setup — all identical in every game.

---

### 🙈 Hide and Seek

Hiders hide with their micro:bits broadcasting their location. The seeker roams
and watches the LEDs to find each hider.

| Version | Micro:bits | Setup |
|---|---|---|
| `hide_and_seek_test/` | 3 | 1 hider (USB relay) + seeker + 1 optional hider |
| `hide_and_seek/` | 3–7 | 1 bridge (USB) + 1 seeker + 1–5 hiders |

**ID assignment:** Hider presses **Button B** at boot to set ID (H1, H2, H3...).
Seeker needs no ID — just start moving.

**Found:** Seeker presses **Button A** when all LEDs light up → dashboard marks
that hider as found.

**⚠️ Recalibrate each session** — hiding spots change every round.

---

### 💎 Treasure Hunt

Treasures are hidden. Hunters roam to find them. Finding is a deliberate
two-step action to prevent false positives.

| Version | Micro:bits | Setup |
|---|---|---|
| `treasure_hunt_test/` | 3 | 1 treasure (USB relay) + 1–2 hunters |
| `treasure_hunt/` | 3–11 | 1 bridge (USB) + 1–5 treasures + 1–5 hunters |

**ID assignment:**
- Hunter presses **Button A** at boot → H1, H2, H3...
- Treasure presses **Button B** at boot → T1, T2, T3...

**Found (two-step — hunter does both presses):**
1. Hunter presses **B** on their **own** micro:bit → announces "I found something"
2. Hunter then presses **B** on the **treasure** micro:bit they picked up
3. Dashboard registers the confirmed find ✅

**Pre-game setup:** Visit `http://localhost:5000/setup` before each game to
set how many hunters and treasures are active.

**⚠️ Recalibrate each session** — hiding spots change every round.

---

## Hardware Requirements

### Minimum (test versions)
- 3 × BBC micro:bit (any version — v1 or v2)
- 2 × battery packs (AAA × 2 each)
- 1 × USB cable (for the relay micro:bit)
- 1 × computer (Windows / macOS / Linux)

### Full versions
- Up to 7–11 × BBC micro:bit
- Battery packs for all non-USB micro:bits
- 1 × USB cable (bridge only)
- 1 × computer **or** Raspberry Pi B+

### Raspberry Pi B+ deployment
Change `SERIAL_PORT` in `config.py`:
```python
SERIAL_PORT = "/dev/ttyACM0"   # run `ls /dev/tty*` to confirm
```
Everything else stays the same. Open the dashboard at `http://<pi-ip>:5000`
from any phone or laptop on the same network.

---

## Flashing micro:bits

**Always use [python.microbit.org/v/3](https://python.microbit.org/v/3)**
(do not use `uflash` — it installs MicroPython v1 which has radio issues on v2 hardware).

1. Open the site → paste the `.py` file content into the editor
2. Plug in the micro:bit via USB
3. Click **Send to micro:bit**
4. Repeat for each device

Flash order for each game is documented in that game's `README.md`.

---

## Running the Computer App

```powershell
cd "D:\Cursor Repositories\<game_folder>\computer_app"
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in any browser.

---

## Code Reuse Map

The table below shows which code blocks are shared across games.
Copy the ✅ blocks directly — no changes needed.

| Code block | Pass Ball | Hide & Seek | Treasure Hunt |
|---|---|---|---|
| `PIXEL_ORDER` list | ✅ source | ✅ identical | ✅ identical |
| `proximity_image()` | ✅ source | ✅ identical | ✅ identical |
| `smooth()` | ✅ source | ✅ identical | ✅ identical |
| Bytes decoding block | ✅ source | ✅ identical | ✅ identical |
| Radio setup | ✅ source | ✅ identical | ✅ identical |
| `mb_bridge.py` | ✅ source | ✅ identical | ✅ identical |
| `serial_reader.py` structure | ✅ source | 🔄 packet format differs | 🔄 packet format differs |
| `app.py` Flask/SocketIO setup | ✅ source | ✅ identical | 🔄 adds setup route |
| `config.py` structure | ✅ source | ✅ identical | ✅ identical |
| RSSI thresholds | calibrate once | ⚠️ each session | ⚠️ each session |

> **⚠️ = must recalibrate** — hiding spots and treasure locations change every round.
> Pass the Ball thresholds are more stable (play area doesn't change as much).

---

## Calibration Guide

RSSI values vary by environment (indoors vs outdoors, walls, furniture).
Always run a quick calibration before a new session:

### Quick method
1. Place the transmitter micro:bit (ball/hider/treasure) at the target distance
2. Watch the LED count on a receiver/seeker/hunter micro:bit
3. If all 25 LEDs are on at the wrong distance, adjust these values in the firmware:
   ```python
   RSSI_HOT   = -50  # ← make less negative (e.g. -40) to require CLOSER range for all LEDs
   RSSI_FLOOR = -80  # ← make more negative (e.g. -90) to push 1-LED range FURTHER away
   ```
4. Re-flash and test again

### Reference readings (indoor, Aug 2026, RADIO_POWER = 3)
| Distance | Typical RSSI |
|---|---|
| Touching | -33 dBm |
| 0.5 m | -53 dBm |
| 1 m | -53 dBm |
| 2 m | -70 dBm |
| 5 m | -83 dBm |
| 6 m | -68 to -83 dBm (variable) |

> Indoor readings vary ±10–15 dBm due to walls and multipath reflections.
> Outdoor readings are generally more consistent.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Dashboard shows "Disconnected" | Wrong COM port or app already running | Check Device Manager, kill other Python processes |
| micro:bit shows sad face / error | Wrong MicroPython version | Re-flash via python.microbit.org |
| LEDs not reacting | Radio group mismatch | Confirm `RADIO_GROUP = 42` in all files |
| All 25 LEDs at wrong distance | RSSI thresholds need calibration | Follow calibration guide above |
| Ball/hider not detected | RADIO_POWER too low | Increase `RADIO_POWER` in transmitter file |
| Multiple devices interfering | Packet collisions | JITTER_MS values already reduce this; increase if needed |

---

## Project History

Built and tested at UNBC, Aug 2026.
Initial calibration data collected indoors with micro:bit v2 hardware.
Designed to be handed off to the next developer with minimal learning curve.

**Next steps for future developers:**
- Outdoor recalibration (new RSSI reference table)
- Multiplayer Bluetooth relay to eliminate USB tether
- Scoring persistence (save tallies between sessions)
- Add sound / buzzer feedback on find events
