# Treasure Hunt — Full Version

A proximity-based Treasure Hunt game for micro:bit.  
**Full version:** dedicated bridge micro:bit + up to 8 hunters + up to 5 treasures.

Optional: add a **Reachy Mini** robot as a narrator and run a player identification
ceremony before gameplay. See [`reachy_mini/README.md`](reachy_mini/README.md) for
the full setup guide.

**First-time init / hotspot reconfig:** [`INITIALIZATION.md`](INITIALIZATION.md)

---

## Hardware Setup

| Role | Micro:bit | Connection |
|---|---|---|
| Bridge (relay) | 1 × micro:bit | USB → PC |
| Treasure 1–5 | 1–5 × micro:bits | Battery packs (placed in the field) |
| Hunter 1–8 | 1–8 × micro:bits | Battery packs (carried by players) |

> Unlike the test version, the bridge micro:bit is a **dedicated relay** — it does not play any game role.  
> Treasures run at `RADIO_POWER=3` (lower power) so proximity can be differentiated.  
> For the Reachy identification flow, hunter micro:bits must be **V2** (gold logo touch sensor required).

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

### Hunter — manual (Button A = set ID, Button B = confirm)
- Power on → display scrolls `H?`
- Press **Button A** once → `H1`, twice → `H2`, up to **H8**
- Press **Button B** to confirm early, or wait 5 s for default **H1**

### Hunter — Reachy identification (V2 only)
When Reachy Mini is enabled on the setup page, a registration ceremony runs
*instead of* (or after) the manual boot window:

1. Hold the **gold logo pad** → micro:bit sends `READY` packets
2. Reachy speaks your name and your secret A/B code
3. Press the three buttons shown on your display
4. Reachy confirms — your `H#` is assigned for this session

See [`reachy_mini/README.md`](reachy_mini/README.md) §8 for the full protocol.

---

## Pre-Game Setup

1. Hide the treasure micro:bits around the play area.
2. (Optional) If you have **not** run `python reachy_mini/reachy_cli.py install`,
   start the agent: `python reachy_mini/reachy_cli.py start`
3. Start the Python app on the connected PC (on Linux / Raspberry Pi use
   `python3` and set `SERIAL_PORT = '/dev/ttyACM0'` in `computer_app/config.py`;
   see [`reachy_mini/LINUX.md`](reachy_mini/LINUX.md)):
   ```
   cd computer_app
   pip install -r requirements.txt
   python app.py
   ```
4. Open your browser at **http://localhost:5000/setup**
5. Choose number of hunters (1–8), treasures (1–5), and optionally enable **Use Reachy Mini**
6. Click **Start Game** (or proceed through the identification screen if Reachy is enabled)

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
| `RG|S|<tok>` | PC→bridge→radio | session start | Begin hunter identification |
| `RG|R|<nonce>|<tok>` | Hunter | logo touched | Hunter ready signal |
| `RG|A|<nonce>|<tok>|<code>` | PC→bridge→radio | assign code | Hunter's secret A/B code |
| `RG|C|<nonce>|<tok>|<code>` | Hunter | code entered | Hunter submitted code |
| `RG|K|<nonce>|<hid>` | PC→bridge→radio | confirm | H# binding confirmed |
| `RG|O|<nonce>|<hid>` | Hunter | ACK | Hunter adopted H# |
| `RG|E` | PC→bridge→radio | end/cancel | Session over |
| `RG|G` | PC→bridge→radio | game start | Hunters play go-jingle |

Bridge forwards all packets as `<message>,<rssi>`. RG| commands are also relayed downward.

---

## Calibration

Edit `computer_app/config.py` and the micro:bit firmware files:

```python
RSSI_HOT   = -50   # dBm — distance where treasure is "found"  <- adjust each session
RSSI_WARM  = -65   # dBm — "getting warmer"                    <- adjust each session
RSSI_FLOOR = -80   # dBm — maximum useful range
```

---

## Optional Reachy Mini

| What it provides | How to enable |
|---|---|
| American female narrator voice | `USE_REACHY = True` in `config.py` |
| Head/antenna emotes on game events | Check **Use Reachy Mini** on setup page |
| Hunter identification ceremony | Requires micro:bit V2 hunters |
| Anonymous face/motion gaze | `"track": true` in `reachy_mini/config.json` |

Reachy is fully optional — **the game runs identically without it.**
If the agent goes offline mid-game, robot events are silently dropped and gameplay continues.

See [`reachy_mini/README.md`](reachy_mini/README.md) for complete setup.

---

## File Overview

```
treasure_hunt/
├── microbit/
│   ├── README.md            # Firmware notes (unchanged on Linux)
│   ├── mb_bridge.py         # Bridge firmware — uplink + RG| downlink relay
│   ├── mb_treasure.py       # Treasure firmware (battery powered, field-deployed)
│   └── mb_hunter.py         # Hunter firmware — manual ID + Reachy registration (V2)
├── computer_app/
│   ├── README.md            # Host app + Linux serial/host notes
│   ├── app.py               # Flask + SocketIO server
│   ├── config.py            # Ports, RSSI thresholds, Reachy settings
│   ├── serial_reader.py     # Serial parser → SocketIO + Reachy events
│   ├── registration.py      # Eight-hunter identification state machine
│   ├── reachy_client.py     # HTTP client for the Reachy Mini agent
│   ├── requirements.txt
│   ├── templates/
│   │   ├── setup.html       # Pre-game configuration (up to 8 hunters, Reachy checkbox)
│   │   ├── initialize.html  # Hunter identification ceremony page
│   │   └── index.html       # Live dashboard
│   └── static/
│       ├── dashboard.js     # SocketIO client + Reachy badge
│       └── initialize.js    # Registration ceremony UI
├── reachy_mini/             # Reachy Mini agent and tools
│   ├── README.md            # Full setup guide
│   ├── LINUX.md             # Windows → Linux / Pi host switch
│   ├── agent.py             # HTTP service (runs ON the robot)
│   ├── robot.py             # Reachy Mini SDK wrapper
│   ├── tracker.py           # Anonymous face/motion gaze
│   ├── reachy_cli.py        # Cross-platform SSH management tool
│   ├── reachy_cli.config.example.json  # Copy to reachy_cli.config.json; set host IP
│   ├── build_voice.py       # Render narration WAV files
│   ├── simulate_agent.py    # Smoke test without a robot
│   ├── config.example.json  # Configuration reference
│   └── audio/
│       ├── voice_lines.json # All narration texts
│       └── *.wav            # Pre-rendered WAVs (generated by build_voice.py)
└── tools/
    └── simulate_registration.py  # Registration protocol headless tests
```

