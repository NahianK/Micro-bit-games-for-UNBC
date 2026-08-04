# Pass the Ball — Micro:bit Proximity Game (Phase 1 Test Build)

## Hardware

| Micro:bit | Role | How to use |
|-----------|------|------------|
| 1 | Ball | Place inside or tape to a physical ball |
| 2 | Player 1 | Held by a child |
| 3 | Player 2 | Held by a child, **USB cable to computer** |

---

## Flashing the Micro:bits

Use [python.microbit.org](https://python.microbit.org) (browser-based MicroPython editor):

1. Open the editor and click **Open** to load each file from `microbit/`
2. Click **Flash** (micro:bit must be plugged in via USB)

| File | Flash onto |
|------|-----------|
| `microbit/mb_ball.py` | Micro:bit 1 |
| `microbit/mb_player.py` | Micro:bit 2 (Player 1) |
| `microbit/mb_player.py` | Micro:bit 3 (Player 2 — keep USB plugged in after flashing) |

### Player ID assignment (on first boot)
- LED shows `ID?`
- Press **Button A** once per player number (1 press = Player 1, 2 presses = Player 2)
- Press **Button B** or wait 5 seconds to confirm
- LED scrolls `P1` or `P2` to confirm

---

## Running the Computer App

### 1. Install Python dependencies (once)
```
cd computer_app
pip install -r requirements.txt
```

### 2. Find your serial port
- Windows: open **Device Manager → Ports** — look for "USB Serial Device (COMx)"
- Raspberry Pi: run `ls /dev/tty*` before and after plugging in — new entry is your port

### 3. Set your serial port
Edit `computer_app/config.py`:
```python
SERIAL_PORT = "COM3"        # Windows example
# SERIAL_PORT = "/dev/ttyACM0"  # Raspberry Pi
```

### 4. Run the app
```
python app.py
```

### 5. Open the dashboard
Navigate to [http://localhost:5000](http://localhost:5000) in any browser.
On Raspberry Pi B+: open `http://<pi-ip-address>:5000` from any device on the same network.

---

## Gameplay

- The ball micro:bit broadcasts continuously
- Each player's LED shows proximity to the ball:
  - **HEART** = very close (HOT — possession range)
  - **ARROW UP** = in range (WARM)
  - **SMALL DOT** = far away (COLD)
- Press **Button A** when your LED shows HEART to claim possession
- The ball's LED shows the holder's number
- Ball is automatically released when it moves away (throw detection)
- The dashboard tracks possession time and count per player live

---

## Tuning RSSI Thresholds

If possession is triggering too easily or not triggering at all, adjust in `computer_app/config.py`:

```python
RSSI_HOT  = -60    # make more negative (e.g. -55) to require closer proximity
RSSI_WARM = -75
```

The same values are set in `microbit/mb_player.py` — update both to match:
```python
RSSI_HOT  = -60
RSSI_WARM = -75
```

---

## Moving to Raspberry Pi B+

1. Copy the entire `computer_app/` folder to the Pi
2. Install dependencies: `pip install -r requirements.txt`
3. Change `SERIAL_PORT` in `config.py` to `/dev/ttyACM0`
4. Run `python app.py` on the Pi
5. Access dashboard at `http://<pi-ip>:5000` from any device on the network

No other code changes needed.

---

## Expanding to More Players

1. Flash `mb_player.py` onto additional micro:bits
2. Assign unique IDs (3, 4, 5) at boot using Button A presses
3. No changes to `mb_ball.py`, `app.py`, or the dashboard — new players appear automatically
