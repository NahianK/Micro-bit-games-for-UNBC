# Treasure Hunt — game host (`computer_app`)

Flask + SocketIO dashboard. Runs on the **game host** (Windows PC or Linux /
Raspberry Pi). It talks to the bridge micro:bit over USB serial and, optionally,
to the Reachy Mini agent over HTTP.

Reachy SDK is **not** installed here. Robot setup: [`../reachy_mini/README.md`](../reachy_mini/README.md).  
Windows → Linux checklist: [`../reachy_mini/LINUX.md`](../reachy_mini/LINUX.md).

---

## Run

```bash
pip install -r requirements.txt    # or: python3 -m pip install -r requirements.txt
python app.py                      # or: python3 app.py
```

Then open `http://localhost:5000/setup`.

---

## Switching this folder to Linux / Raspberry Pi OS

Only **`config.py`** needs editing. The other `.py` files are already
cross-platform.

| Key in `config.py` | Windows | Linux / Pi |
|--------------------|---------|------------|
| `SERIAL_PORT` | `'COM3'` | `'/dev/ttyACM0'` (try `'/dev/ttyUSB0'` if ACM is missing) |
| `REACHY_AGENT_HOST` | often `'192.168.1.65'` | `'reachy-mini.local'` or the same IP |
| `REACHY_AGENT_PORT` | `7000` | leave `7000` |

Also on Linux:

- Add your user to `dialout` so serial works: `sudo usermod -aG dialout $USER` (then log out/in).
- Confirm the bridge device: `ls /dev/ttyACM* /dev/ttyUSB*`.
- Use `python3` if `python` is not on PATH.

Do **not** change `app.py`, `serial_reader.py`, `reachy_client.py`, or
`registration.py` just because the host OS changed.
