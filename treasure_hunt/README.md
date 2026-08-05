# Treasure Hunt — Full Version

A proximity-based Treasure Hunt game for micro:bit.  
**Full version:** dedicated bridge micro:bit + up to 5 hunters + up to 5 treasures.

---

## Hardware Setup

| Role | Micro:bit | Connection |
|---|---|---|
| Bridge (relay) | 1 × micro:bit | USB → PC |
| Treasure 1–5 | 1–5 × micro:bits | Battery packs (placed in the field) |
| Hunter 1–5 | 1–5 × micro:bits | Battery packs (carried by players) |

> Unlike the test version, the bridge micro:bit is a **dedicated relay** — it does not play any game role.  
> Treasures run at `RADIO_POWER=3` (lower power) so proximity can be differentiated.

---

## Flashing Instructions

1. **Bridge micro:bit** → flash `microbit/mb_bridge.py` (USB → PC)
2. **Treasure micro:bits** → flash `microbit/mb_treasure.py` (battery packs, placed in the field)
3. **Hunter micro:bits** → flash `microbit/mb_hunter.py` (battery packs, carried by players)

Use [Mu Editor](https://codewith.mu/) or the online [micro:bit Python editor](https://python.microbit.org/).

---

## ID Assignment (5-second boot window)

### Treasure (Button B = set ID, Button A = confirm)
- Power on → display scrolls `T?`
- Press **Button B** once → `T1`, twice → `T2`, up to **T5**
- Press **Button A** to confirm early, or wait 5 s for default **T1**

### Hunter (Button A = set ID, Button B = confirm)
- Power on → display scrolls `H?`
- Press **Button A** once → `H1`, twice → `H2`, up to **H5**
- Press **Button B** to confirm early, or wait 5 s for default **H1**

---

## Pre-Game Setup

1. Hide the treasure micro:bits around the play area.
2. Start the Python app on the connected PC:
   ```
   cd computer_app
   pip install -r requirements.txt
   python app.py
   ```
3. Open your browser at **http://localhost:5000/setup**
4. Choose number of hunters and treasures → click **Start Game**

---

## FOUND Mechanic (Two-Step)

Finding a treasure requires **two** Button B presses:

1. **Hunter presses Button B on their own micro:bit**  
   → broadcasts `CLAIM:H<id>` ("I've found something!")  
   → display scrolls `FIND!`

2. **Hunter then presses Button B on the TREASURE micro:bit** they are holding  
   → treasure hears the recent CLAIM and broadcasts `FOUND:T<id>:H<id>`  
   → treasure displays ✔, dashboard marks it found

> ⏱ The treasure accepts a CLAIM for **10 seconds** after it is received.

---

## Radio Protocol Summary

| Message | Sent by | Format | Meaning |
|---|---|---|---|
| `TRS:T1` | Treasure | broadcast every ~300ms | "I'm here" beacon |
| `HUNT:H1:T1:-65` | Hunter | after receiving TRS | Proximity re-broadcast |
| `CLAIM:H1` | Hunter | Button B press | "I think I found one!" |
| `FOUND:T1:H1` | Treasure | Button B press + recent CLAIM | Confirmed find |

Bridge forwards everything as `<message>,<rssi>`.

---

## Calibration

Edit `computer_app/config.py` and the micro:bit firmware files:

```python
RSSI_HOT   = -50   # dBm — distance where treasure is "found"  <- adjust each session
RSSI_WARM  = -65   # dBm — "getting warmer"                    <- adjust each session
RSSI_FLOOR = -80   # dBm — maximum useful range
```

---

## Code Reuse Table

| File | Reused from |
|---|---|
| `microbit/mb_hunter.py` | Identical to `treasure_hunt_test/microbit/mb_hunter.py` |
| `microbit/mb_treasure.py` | Same as test version, minus serial relay section |
| `microbit/mb_bridge.py` | Copied from `pass_the_ball_test_5_players/microbit/mb_bridge.py` |
| `computer_app/config.py` | Same structure as all game configs |
| `computer_app/serial_reader.py` | Identical to test version |
| `computer_app/app.py` | Identical to test version |
| `computer_app/static/dashboard.js` | Identical to test version |
| `computer_app/templates/setup.html` | Identical to test version |
| `computer_app/templates/index.html` | Same as test, title updated for full version |

---

## File Overview

```
treasure_hunt/
├── microbit/
│   ├── mb_bridge.py     # Bridge/relay firmware (copied from pass_the_ball)
│   ├── mb_treasure.py   # Treasure firmware (battery powered, field-deployed)
│   └── mb_hunter.py     # Hunter firmware (identical to test version)
└── computer_app/
    ├── app.py           # Flask + SocketIO server
    ├── config.py        # Ports, RSSI thresholds
    ├── serial_reader.py # Serial parser → SocketIO events
    ├── requirements.txt
    ├── templates/
    │   ├── setup.html   # Pre-game configuration page
    │   └── index.html   # Live dashboard (Full Version)
    └── static/
        └── dashboard.js # SocketIO client
```
