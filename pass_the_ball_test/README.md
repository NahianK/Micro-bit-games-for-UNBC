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

### On Windows (development / testing)

#### 1. Install Python dependencies (once)
```
cd computer_app
pip install -r requirements.txt
```

#### 2. Run the app
```
python app.py
```
The serial port is **auto-detected** — no config change needed.
Override with an environment variable if necessary:
```
set MICROBIT_PORT=COM4 && python app.py
```

#### 3. Open the dashboard
Navigate to [http://localhost:5000](http://localhost:5000) in any browser.

---

### On Raspberry Pi B+ or Pi 5

#### 1. Copy the repo to the Pi
```bash
git clone <your-repo-url> ~/pass_the_ball
# or: scp -r pass_the_ball_test pi@<pi-ip>:~/pass_the_ball
```

#### 2. Run the one-shot setup script
```bash
cd ~/pass_the_ball
bash setup_pi.sh
```

This script:
- Installs Python dependencies
- Adds your user to the `dialout` group (serial port access)
- Installs and **enables a systemd service** so the dashboard starts automatically on boot

#### 3. Open the dashboard
```
http://<pi-ip-address>:5000
```
from any device on the same network.

#### Useful Pi commands
```bash
sudo systemctl status pass-the-ball   # check if running
journalctl -u pass-the-ball -f        # live log
sudo systemctl restart pass-the-ball  # restart after a code change
```

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

## Moving from Pi 5 to Pi B+

No code changes needed — the serial port is auto-detected and the systemd service is identical.

1. Copy the repo to the Pi B+
2. Run `bash setup_pi.sh` (same script)
3. Access dashboard at `http://<pi-b-plus-ip>:5000`

> **Pi B+ note:** The B+ is slower but handles this app fine.
> If the dashboard feels sluggish on the B+, reduce `SMOOTH_WINDOW` in `config.py`
> to `3` to lower CPU usage from serial processing.

---

## Expanding to More Players

1. Flash `mb_player.py` onto additional micro:bits
2. Assign unique IDs (3, 4, 5) at boot using Button A presses
3. No changes to `mb_ball.py`, `app.py`, or the dashboard — new players appear automatically
