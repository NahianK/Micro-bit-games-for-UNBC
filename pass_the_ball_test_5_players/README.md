# Pass the Ball — 6 Micro:bit Version (2–5 Players)

> **Version:** 6 micro:bits — 1 dedicated bridge + 1 ball + 2–5 players  
> **Language:** MicroPython (micro:bit) + Python/Flask (computer)  
> **Requires:** Python 3.9+, pip, micro:bit v2 ×6 (fewer for fewer players)

---

## Hardware Layout

| Micro:bit | Role | USB? | Moves? |
|---|---|---|---|
| **Micro:bit 1** | Bridge | ✅ Plugged into PC/Pi at all times | ❌ Stationary |
| **Micro:bit 2** | Ball | ❌ Battery powered | ✅ Inside the ball |
| **Micro:bits 3–7** | Players 1–5 | ❌ Battery powered | ✅ Free-moving |

**Minimum setup:** 1 bridge + 1 ball + 2 players = 4 micro:bits total.  
**Maximum:** 1 bridge + 1 ball + 5 players = 7 micro:bits total.

The bridge is stationary and game-agnostic — it simply relays all radio traffic to the computer. Players and ball are completely wireless.

---

## Quick Start

### 1 — Install Python dependencies
```bash
cd computer_app
pip install -r requirements.txt
```

### 2 — Flash all micro:bits via [python.microbit.org/v/3](https://python.microbit.org/v/3)

Flash each device in order. Paste the file contents, click **Send to micro:bit**, then click **Disconnect** in the editor before unplugging.

| Device | File | Expected LED after boot |
|---|---|---|
| Bridge (Micro:bit 1) | `microbit/mb_bridge.py` | Downward arrow (↓) |
| Ball (Micro:bit 2) | `microbit/mb_ball.py` | Diamond + scrolls "BALL" |
| Each player | `microbit/mb_player.py` | 1 centre dot (after ID setup) |

### 3 — Set player IDs

Each player micro:bit shows **"ID?"** for 5 seconds on boot.  
Press **Button A** once per player number:
- 1 press = Player 1
- 2 presses = Player 2
- 3 presses = Player 3
- 4 presses = Player 4
- 5 presses = Player 5

Press **Button B** at any time to confirm immediately.  
If no button is pressed, the device defaults to **Player 1**.

### 4 — Power all devices

- **Bridge:** leave plugged into computer USB
- **Ball + all players:** connect battery packs

### 5 — Start the dashboard

```bash
cd computer_app
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in a browser.  
On Raspberry Pi B+: open `http://<pi-ip-address>:5000` from any device on the network.

---

## Gameplay

1. The ball micro:bit constantly broadcasts its presence over radio
2. Each player's LED matrix fills from the centre outward as the ball gets closer
3. When a player's LEDs are **fully lit** (ball within ~0.5m) they can press **Button A** to claim possession
4. The ball micro:bit displays the holder's number
5. Possession is automatically released when the ball is thrown away (signal drops below RSSI_WARM threshold)
6. The dashboard tracks each player's signal strength, time in possession, and possession count in real time

---

## Calibration

Signal thresholds are tuned for indoor use with `RADIO_POWER = 3` on the ball. Recalibrate outdoors or in a large open space for best results.

**To recalibrate:**
1. Run `python diagnose_serial.py` (stop `app.py` first)
2. Hold ball at each distance from a player and note the `P1:` RSSI values
3. Update the three constants marked `← CALIBRATE THIS` in `microbit/mb_player.py`:

```python
RSSI_HOT   = -50   # your touching/0.5m reading
RSSI_WARM  = -65   # halfway between HOT and FLOOR
RSSI_FLOOR = -80   # your max game distance reading
```

4. Update matching values in `computer_app/config.py`:

```python
RSSI_HOT  = -50
RSSI_WARM = -65
```

5. Reflash all player micro:bits and restart `app.py`

> **Note for Hide & Seek and Treasure Hunt:** Those games require on-the-spot calibration each session because the hiding location and room geometry change every game. Use `diagnose_serial.py` to measure at the specific spot before each game.

---

## Raspberry Pi B+ Deployment

1. Copy the entire `computer_app/` folder to the Pi
2. Install dependencies: `pip3 install -r requirements.txt`
3. Edit `config.py`: change `SERIAL_PORT = "COM3"` to `SERIAL_PORT = "/dev/ttyACM0"`
4. Plug the bridge micro:bit into a Pi USB port
5. Run: `python3 app.py`
6. Access from any device: `http://<pi-ip>:5000`

---

## File Structure

```
pass_the_ball_test_5_players/
├── microbit/
│   ├── mb_bridge.py      # Bridge firmware — game-agnostic, reuse for all games
│   ├── mb_ball.py        # Ball firmware — reuse for Treasure Hunt
│   └── mb_player.py      # Player firmware — reuse structure for all games
└── computer_app/
    ├── app.py            # Flask + Socket.IO server
    ├── config.py         # All tunable settings ← calibrate here
    ├── serial_reader.py  # Bridge serial parser
    ├── diagnose_serial.py # Raw serial monitor for calibration
    ├── requirements.txt
    ├── templates/
    │   └── index.html    # Dashboard HTML
    └── static/
        └── dashboard.js  # Real-time dashboard logic
```

---

## Code Reuse Guide

| Component | Reusable? | Notes |
|---|---|---|
| `mb_bridge.py` | ✅ Identical | No changes needed for any game |
| `smooth()` function | ✅ Identical | Copy to all player firmware |
| `PIXEL_ORDER` + `proximity_image()` | ✅ Identical | Copy to all player firmware |
| Radio setup block | ✅ Identical | Same group, same config |
| Bytes decoding block | ✅ Identical | Required for MicroPython v2 |
| HOLDER claim logic | 🔄 Game-specific | Remove for Hide & Seek / Treasure Hunt |
| Ball broadcast message | 🔄 Game-specific | Change "BALL" → "TREASURE" or "HIDE:<id>" |
| `config.py` structure | ✅ Identical | Only thresholds change |
| `serial_reader.py` parsing | 🔄 Minor changes | Update message prefix matching per game |
| `app.py` Flask structure | ✅ Identical | Same server, same Socket.IO events |
| `dashboard.js` | 🔄 Minor changes | Add game-specific UI elements |
