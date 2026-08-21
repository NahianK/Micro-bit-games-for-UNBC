# Switching Treasure Hunt + Reachy Mini to Linux

Use this when the game host moves from Windows to **Linux or Raspberry Pi OS**
(including a Raspberry Pi B+). The robot itself does not change.

Python files in this folder (`agent.py`, `robot.py`, `tracker.py`) run **on the
Reachy Mini**, not on the Pi. Do not edit them for a Linux host switch.

Full setup: [README.md](README.md). Game-host serial/network: [`../computer_app/README.md`](../computer_app/README.md).

---

## What you must change

| Setting | Windows (current) | Linux / Raspberry Pi OS |
|---------|-------------------|-------------------------|
| Serial port | `COM3` (or `COM4`…) | `/dev/ttyACM0` (sometimes `/dev/ttyUSB0`) |
| Reachy host | Often a numeric IP | `reachy-mini.local` usually works; IP is still fine |
| Python | `python` | `python3` (or a venv) |
| SSH key copy | PowerShell snippet in README §2 | `ssh-copy-id pollen@reachy-mini.local` |
| Piper binary | `piper.exe` | `piper` for linux-x86_64 or linux-arm64 (Pi) |

Edit only `computer_app/config.py` on the game host:

```python
SERIAL_PORT = '/dev/ttyACM0'
REACHY_AGENT_HOST = 'reachy-mini.local'   # or keep 192.168.1.65
```

Leave `REACHY_AGENT_PORT = 7000` unchanged.

---

## One-time on the Linux host

1. Plug in the **bridge** micro:bit over USB. Confirm the device:

   ```bash
   ls /dev/ttyACM* /dev/ttyUSB*
   ```

2. Let the game user open serial ports (Raspberry Pi OS / Debian / Ubuntu):

   ```bash
   sudo usermod -aG dialout $USER
   ```

   Log out and back in (or reboot) so the group takes effect.

3. Install app packages:

   ```bash
   cd computer_app
   python3 -m pip install -r requirements.txt
   ```

4. SSH key to the robot (password is `root` the first time):

   ```bash
   ssh-keygen -t ed25519 -C "treasure-hunt"   # skip if you already have a key
   ssh-copy-id pollen@reachy-mini.local
   ssh pollen@reachy-mini.local echo OK
   ```

5. Copy CLI config and set the robot host (once per machine):

   ```bash
   cd reachy_mini
   cp reachy_cli.config.example.json reachy_cli.config.json
   # edit host if needed, e.g. pollen@192.168.1.65 or pollen@reachy-mini.local
   ```

6. Deploy and enable auto-start **from this folder** (once):

   ```bash
   python3 reachy_cli.py install
   python3 reachy_cli.py status
   ```

   After `install`, skip manual `start` before each game.

If `.local` does not resolve, put the LAN IP in `reachy_cli.config.json`, then:

```bash
python3 reachy_cli.py check
```

---

## Each session

```bash
cd ../computer_app && python3 app.py
```

Open `http://localhost:5000/setup` on the Pi, or `http://<pi-ip>:5000/setup`
from another machine on the same LAN. Check **Use Reachy Mini**.

Only run `python3 reachy_cli.py start` if you did **not** run `install`.

---

## What you do not need to change

- `agent.py` / `robot.py` / `tracker.py` — already Linux on the robot’s CM4.
- `reachy_cli.py` — same commands; use `python3` instead of `python` if needed.
- `config.example.json` on the robot — port 7000 stays the same.
- Pre-built `audio/*.wav` — copy them with `deploy`; no rebuild required on the Pi.
- micro:bit firmware in `../microbit/` — OS-independent.

Voice rebuild (optional, usually done on a PC): download the Linux Piper binary
and run `python3 build_voice.py --piper /path/to/piper --model /path/to/en_US-amy-medium.onnx`.
