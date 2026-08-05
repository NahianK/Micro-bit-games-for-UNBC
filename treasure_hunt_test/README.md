# Treasure Hunt — TEST Version (3 micro:bits)

A proximity-based Treasure Hunt game for micro:bit.  
**Test version:** 1 treasure (USB relay) + 1–2 hunters.

---

## Hardware Setup

| Role | Micro:bit | Connection |
|---|---|---|
| Treasure / Relay | 1 × micro:bit | USB → PC |
| Hunter 1 | 1 × micro:bit | Battery pack |
| Hunter 2 (optional) | 1 × micro:bit | Battery pack |

> In this test version **Treasure T1 doubles as the radio relay**.  
> It is plugged into the PC via USB and forwards all radio packets to serial.

---

## Flashing Instructions

1. **Treasure micro:bit** → flash `microbit/mb_treasure.py`  
   (keep it plugged into USB)

2. **Hunter micro:bits** → flash `microbit/mb_hunter.py`  
   (battery powered)

Use [Mu Editor](https://codewith.mu/) or the online [micro:bit Python editor](https://python.microbit.org/).

---

## ID Assignment (5-second boot window)

### Treasure (Button B = set ID, Button A = confirm)
- Power on → display scrolls `T?`
- Press **Button B** once → `T1`, twice → `T2`, etc.  
- Press **Button A** to confirm early, or wait 5 s for default **T1**

### Hunter (Button A = set ID, Button B = confirm)
- Power on → display scrolls `H?`
- Press **Button A** once → `H1`, twice → `H2`, etc.  
- Press **Button B** to confirm early, or wait 5 s for default **H1**

---

## Pre-Game Setup

1. Start the Python app:
   ```
   cd computer_app
   pip install -r requirements.txt
   python app.py
   ```
2. Open your browser at **http://localhost:5000/setup**
3. Choose number of hunters and treasures → click **Start Game**

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
> If Button B is not pressed on the treasure within that window, try again.

---

## Calibration

Edit `computer_app/config.py` and `microbit/mb_hunter.py` / `microbit/mb_treasure.py`:

```python
RSSI_HOT   = -50   # dBm — distance where treasure is "found"  <- adjust each session
RSSI_WARM  = -65   # dBm — "getting warmer"                    <- adjust each session
RSSI_FLOOR = -80   # dBm — maximum useful range
```

Walk a known distance (e.g. 0.5 m) from the treasure micro:bit and read the RSSI  
shown in the Mu REPL or the dashboard to set realistic values.

---

## File Overview

```
treasure_hunt_test/
├── microbit/
│   ├── mb_treasure.py   # Treasure firmware (also relay in test mode)
│   └── mb_hunter.py     # Hunter firmware
└── computer_app/
    ├── app.py           # Flask + SocketIO server
    ├── config.py        # Ports, RSSI thresholds
    ├── serial_reader.py # Serial parser → SocketIO events
    ├── requirements.txt
    ├── templates/
    │   ├── setup.html   # Pre-game configuration page
    │   └── index.html   # Live dashboard
    └── static/
        └── dashboard.js # SocketIO client
```
