# Treasure Hunt — Initialization Manual

Step-by-step ops guide for first-time setup, Reachy Mini bring-up, and
reconfiguration when the robot or PC joins a different Wi‑Fi hotspot.

Related docs (detail / reference):

- Game overview: [`README.md`](README.md)
- Host app notes: [`computer_app/README.md`](computer_app/README.md)
- Reachy agent: [`reachy_mini/README.md`](reachy_mini/README.md)
- Host OS switch: [`reachy_mini/LINUX.md`](reachy_mini/LINUX.md)
- Firmware notes: [`microbit/README.md`](microbit/README.md)

Throughout this doc, replace **`insert path here`** with your local clone of
`treasure_hunt` (folder locations change between machines). Do not assume a
fixed `C:\…` path.

---

## 1. Prerequisites

### Hardware

| Item | Notes |
|------|--------|
| Bridge micro:bit | USB → game host PC (dedicated relay, no game role) |
| Hunter micro:bits (1–8) | Battery packs; **V2** required for Reachy identification (gold logo touch) |
| Treasure micro:bits (1–5) | Battery packs, placed in the field |
| Game host PC | Windows or Linux / Raspberry Pi; Python **3.12** preferred |
| Reachy Mini (optional) | Wireless CM4; SSH user `pollen`; daemon on port **8000**; agent on **7000** |

### Software on the game host

- Python 3.12 (or 3.8+ if 3.12 is unavailable)
- OpenSSH client (`ssh` / `scp` in PATH) — only if using Reachy
- [Mu Editor](https://codewith.mu/) or [micro:bit Python editor](https://python.microbit.org/) for flashing
- Piper TTS (optional, PC-only) to build narration WAVs for Reachy

### Typical LAN addresses (historical reference — yours will differ)

| Device | Example |
|--------|---------|
| Reachy Mini | `192.168.1.65` (SSH: `pollen@…`) |
| Game host PC | `192.168.1.64` |
| Agent HTTP | port `7000` |
| Reachy daemon | port `8000` (`http://<robot-ip>:8000/`) |

---

## 2. PC / computer_app — first-time setup

### 2.1 Open a terminal in the host app folder

**Windows (PowerShell or cmd):**

```powershell
cd "insert path here\treasure_hunt\computer_app"
```

**Linux / macOS / Raspberry Pi OS:**

```bash
cd "insert path here/treasure_hunt/computer_app"   # same idea; use forward slashes
```

### 2.2 (Optional) Create a virtual environment

**Windows:**

```powershell
py -3.12 -m venv .venv                          # Linux: python3.12 -m venv .venv  (or python3 -m venv .venv)
.\.venv\Scripts\Activate.ps1                    # Linux: source .venv/bin/activate
```

**Linux:**

```bash
python3.12 -m venv .venv                        # Windows: py -3.12 -m venv .venv
source .venv/bin/activate                       # Windows PowerShell: .\.venv\Scripts\Activate.ps1
```

### 2.3 Install required Python packages

From `computer_app` (packages from `requirements.txt`: Flask, Flask-SocketIO, pyserial):

**Windows:**

```powershell
py -3.12 -m pip install -r requirements.txt     # Linux: python3 -m pip install -r requirements.txt
```

**Linux:**

```bash
python3 -m pip install -r requirements.txt      # Windows: py -3.12 -m pip install -r requirements.txt
```

Equivalent one-liner if you prefer naming packages explicitly:

```powershell
py -3.12 -m pip install "flask>=2.3" "flask-socketio>=5.3" "pyserial>=3.5"   # Linux: python3 -m pip install …
```

---

## 3. Micro:bit flashing

Flash with Mu or the online micro:bit Python editor. Firmware does **not**
change between Windows and Linux hosts.

| Role | Firmware file | Power / connection |
|------|---------------|--------------------|
| Bridge | `microbit/mb_bridge.py` | USB → game host |
| Treasure | `microbit/mb_treasure.py` | Battery; place in field |
| Hunter | `microbit/mb_hunter.py` | Battery; carried by players |

### ID assignment (5-second boot window)

**Treasure** — Button B cycles ID, Button A confirms:

- Power on → `T?` → B → `T1`…`T5` → A (or wait 5 s → default T1)

**Hunter (manual)** — Button A cycles ID, Button B confirms:

- Power on → `H?` → A → `H1`…`H8` → B (or wait 5 s → default H1)

**Hunter (Reachy ceremony)** — when Reachy is enabled, V2 hunters use the gold
logo touch + A/B code flow instead (see §8). Diamond latch registration is in
`mb_hunter.py`.

After flashing, leave the **bridge** plugged into the host USB for the game.

---

## 4. Config edits (`computer_app/config.py`)

Edit only what your hardware/network requires.

### 4.0 Enable Reachy Mini (required for the robot) — do not skip

Open **`computer_app/config.py`** and set this line explicitly:

```python
USE_REACHY = True
```

| Value | Effect |
|-------|--------|
| `USE_REACHY = False` | Normal hunt only — no robot HTTP calls |
| `USE_REACHY = True` | When you run `app.py`, the host calls the agent **`POST /init`**: full Reachy bring-up (wake, **voice**/speaker path, **camera tracking**). The setup page can then run the identification ceremony. |

Without this `True`, the setup page shows “Reachy Mini: disabled” and the robot stays unused even if the agent is running on the robot.

Also set the agent address (same file):

```python
SERIAL_PORT = 'COM3'              # Linux / Pi: '/dev/ttyACM0'  (or '/dev/ttyUSB0')
BAUD_RATE = 115200

USE_REACHY = True                 # <<< must be True to use the robot (see §4.0)
REACHY_AGENT_HOST = '192.168.1.65'  # Linux often: 'reachy-mini.local' or the robot's IP
REACHY_AGENT_PORT = 7000          # must match robot agent bind_port
REACHY_AGENT_TOKEN = ''           # must match robot config.json token if set
```

### Discover the serial port

**Windows:** Device Manager → Ports (COM & LPT), or:

```powershell
mode                                   # look for COMn; Linux: ls /dev/ttyACM* /dev/ttyUSB*
```

**Linux:**

```bash
ls /dev/ttyACM* /dev/ttyUSB*           # Windows: check Device Manager for COMn
sudo usermod -aG dialout $USER         # once; then log out/in — Windows: not needed
```

### Linux vs Windows cheat-sheet (same-line notes)

```python
SERIAL_PORT = 'COM3'                   # Linux: SERIAL_PORT = '/dev/ttyACM0'
REACHY_AGENT_HOST = '192.168.1.65'     # Linux: often 'reachy-mini.local'
USE_REACHY = True                      # same on Linux; False disables the robot
```

```powershell
py -3.12 app.py                        # Linux: python3 app.py
```

Do **not** edit `app.py`, `serial_reader.py`, `reachy_client.py`, or
`registration.py` just because the host OS changed.

---

## 5. Running the game **without** Reachy

1. In `computer_app/config.py` set `USE_REACHY = False`.
2. Plug in the bridge micro:bit; set `SERIAL_PORT` correctly.
3. Start the app:

```powershell
cd "insert path here\treasure_hunt\computer_app"
py -3.12 app.py                        # Linux: python3 app.py
```

4. Open `http://localhost:5000/setup`
5. Choose hunters (1–8) and treasures (1–5); leave **Use Reachy Mini** unchecked
6. Click **Start Game**

Gameplay works fully without the robot. If Reachy is offline mid-game, robot
events are dropped and the hunt continues.

---

## 6. First-time Reachy Mini setup

Do this once per robot + game-host pair (or after a wipe). Agent code runs
**on the robot** under `/home/pollen/treasure_hunt_reachy/`. The Reachy SDK
is **not** installed on the PC.

### 6.1 Network and reachability

1. Power on Reachy Mini; join the same Wi‑Fi as the game host (robot remembers
   the network after first join — use the Reachy Control / daemon UI if needed:
   `http://reachy-mini.local:8000/` or `http://<robot-ip>:8000/`).
2. Note the robot IP (DHCP table, daemon UI, or `ping`).
3. From the game host:

```powershell
ping 192.168.1.65                      # replace with your robot IP; Linux: same, or ping reachy-mini.local
```

**Windows SSH tip:** if SSH stalls or is flaky, add QoS override:

```powershell
ssh -o IPQoS=none pollen@192.168.1.65  # Linux: usually unnecessary; plain ssh is fine
```

### 6.2 SSH key (once per game host)

**Windows (PowerShell):**

```powershell
ssh-keygen -t ed25519 -C "treasure-hunt"   # skip if you already have a key
$pubkey = Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
ssh -o IPQoS=none pollen@insert-robot-ip-here "mkdir -p ~/.ssh && echo '$pubkey' >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
# Default first-time password is often root — change after setup if required
```

**Linux / macOS:**

```bash
ssh-keygen -t ed25519 -C "treasure-hunt"   # skip if you already have a key
ssh-copy-id pollen@insert-robot-ip-here    # Windows: use the PowerShell snippet above instead
ssh pollen@insert-robot-ip-here echo OK
```

### 6.3 CLI config on the PC

```powershell
cd "insert path here\treasure_hunt\reachy_mini"
copy reachy_cli.config.example.json reachy_cli.config.json   # Linux: cp reachy_cli.config.example.json reachy_cli.config.json
```

Edit `reachy_cli.config.json`:

```json
{
  "host": "pollen@insert-robot-ip-here",
  "agent_port": 7000,
  "remote_dir": "/home/pollen/treasure_hunt_reachy"
}
```

### 6.4 Build voice WAVs on the PC (once)

Piper runs on the **PC**; outputs go to `reachy_mini/audio/`.

1. Download Piper voice `en_US-amy-medium` (`.onnx` + `.onnx.json`) from Hugging Face.
2. Download the Piper binary for your OS.
3. Render:

```powershell
cd "insert path here\treasure_hunt\reachy_mini"
py -3.12 build_voice.py --piper "insert path here\piper.exe" --model "insert path here\en_US-amy-medium.onnx"
# Linux: python3 build_voice.py --piper "insert path here/piper" --model "insert path here/en_US-amy-medium.onnx"
```

Fallback without Piper:

```powershell
py -3.12 -m pip install pyttsx3            # Linux: python3 -m pip install pyttsx3
py -3.12 build_voice.py                    # Linux: python3 build_voice.py
```

### 6.5 Deploy agent / robot / audio / config to the robot

**Preferred (when scp works):**

```powershell
cd "insert path here\treasure_hunt\reachy_mini"
py -3.12 reachy_cli.py check               # Linux: python3 reachy_cli.py check
py -3.12 reachy_cli.py deploy              # copies agent.py, robot.py, tracker.py, audio/
# or one-shot with systemd auto-start:
py -3.12 reachy_cli.py install             # Linux: python3 reachy_cli.py install
```

Remote layout after deploy:

| On robot | Purpose |
|----------|---------|
| `/home/pollen/treasure_hunt_reachy/agent.py` | HTTP agent (port 7000) |
| `/home/pollen/treasure_hunt_reachy/robot.py` | SDK wrapper (talks to daemon :8000) |
| `/home/pollen/treasure_hunt_reachy/tracker.py` | Optional gaze |
| `/home/pollen/treasure_hunt_reachy/audio/` | Narration WAVs |
| `/home/pollen/treasure_hunt_reachy/config.json` | Created from example on first deploy |

**If `scp` hangs on Windows:** serve files from the PC and pull with `wget` on the robot.

On the PC (from `reachy_mini`):

```powershell
cd "insert path here\treasure_hunt\reachy_mini"
py -3.12 -m http.server 8080               # Linux: python3 -m http.server 8080
```

On the robot (SSH), replace `insert-pc-ip-here` (historical example: `192.168.1.64`):

```bash
mkdir -p /home/pollen/treasure_hunt_reachy/audio
cd /home/pollen/treasure_hunt_reachy
wget -O agent.py   http://insert-pc-ip-here:8080/agent.py
wget -O robot.py   http://insert-pc-ip-here:8080/robot.py
wget -O tracker.py http://insert-pc-ip-here:8080/tracker.py
wget -O config.example.json http://insert-pc-ip-here:8080/config.example.json
# Pull audio files similarly (or wget -r / recursive mirror of /audio/)
test -f config.json || cp config.example.json config.json
```

### 6.6 Python venv on the robot

Use the **mini daemon** venv (has the Reachy SDK tied to the running daemon):

```text
/venvs/mini_daemon/bin/python
```

Do **not** use `/venvs/apps_venv/bin/python` for this agent unless you have
verified that venv has a matching SDK. Note: `reachy_cli.py` may still
reference `apps_venv` in its built-in constant — if `check`/`start` fail on
venv, start manually with `mini_daemon` (below) or adjust the CLI on your
machine.

### 6.7 Configure and start the agent

Edit robot config if needed:

```bash
ssh -o IPQoS=none pollen@insert-robot-ip-here   # Linux: ssh pollen@insert-robot-ip-here
nano /home/pollen/treasure_hunt_reachy/config.json
```

Confirm at least:

- `bind_port`: `7000`
- `audio_dir`: `/home/pollen/treasure_hunt_reachy/audio`
- `token`: empty string, or the same value as `REACHY_AGENT_TOKEN` on the PC

**Auto-start (after `reachy_cli.py install`):** reboot or

```powershell
py -3.12 reachy_cli.py start               # Linux: python3 reachy_cli.py start
py -3.12 reachy_cli.py status
```

**Manual start (SSH on robot):**

```bash
cd /home/pollen/treasure_hunt_reachy
/venvs/mini_daemon/bin/python agent.py --config /home/pollen/treasure_hunt_reachy/config.json
# Do not use /venvs/apps_venv/bin/python unless you know it matches the daemon SDK
```

### 6.8 Verify port 7000

From the game host:

```powershell
curl http://insert-robot-ip-here:7000/health   # Linux: same; or: curl http://reachy-mini.local:7000/health
py -3.12 reachy_cli.py status                  # Linux: python3 reachy_cli.py status
```

If the process is up but health fails, open the firewall on the robot:

```bash
ssh pollen@insert-robot-ip-here "sudo ufw allow 7000/tcp"
```

### 6.9 Point the game host at the robot (REQUIRED)

In **`computer_app/config.py`** — this is the switch that turns the robot on
from the game host:

```python
USE_REACHY = True                      # <<< REQUIRED — must be True
REACHY_AGENT_HOST = 'insert-robot-ip-here'   # Linux: IP or 'reachy-mini.local'
REACHY_AGENT_PORT = 7000
```

With `USE_REACHY = True`, starting `app.py` (and again when you start a Reachy
session from `/setup`) calls the agent **`POST /init`**, which brings up the
**whole** Reachy Mini: wake, speaker/voice narration path, and **camera
tracking** — not just a health ping.

**Redeploy the agent** after pulling these changes so the robot has `/init`
(agent version **1.2+**):

```powershell
cd "insert path here\treasure_hunt\reachy_mini"
py -3.12 reachy_cli.py deploy              # Linux: python3 reachy_cli.py deploy
py -3.12 reachy_cli.py start               # or: restart the systemd service
```

Then run `app.py` (§8) and check **Use Reachy Mini** on `/setup`.

---

## 7. Reconfiguration for a **different Wi‑Fi hotspot**

When Reachy and/or the PC move to a new SSID, IPs almost always change.

### 7.1 Join the new network

1. Connect the **game host** to the new hotspot.
2. Connect **Reachy Mini** to the same hotspot (daemon UI / Control app / robot
   Wi‑Fi settings). Wait until the robot has a DHCP lease.
3. Discover the **new robot IP** and **new PC IP** (router page, daemon UI,
   `ipconfig` / `ip addr`).

```powershell
ipconfig                                   # Linux: ip addr   or   hostname -I
ping insert-new-robot-ip-here
ssh -o IPQoS=none pollen@insert-new-robot-ip-here echo OK   # Linux: omit IPQoS if not needed
```

### 7.2 Update PC config

`computer_app/config.py`:

```python
REACHY_AGENT_HOST = 'insert-new-robot-ip-here'   # Linux: IP or reachy-mini.local if mDNS works on the new LAN
```

`reachy_mini/reachy_cli.config.json`:

```json
"host": "pollen@insert-new-robot-ip-here"
```

### 7.3 Robot-side checks

Usually **no** edit is required on the robot for a new hotspot if the agent
still binds `0.0.0.0:7000`. Restart the agent so it comes up cleanly on the new
lease:

```powershell
cd "insert path here\treasure_hunt\reachy_mini"
py -3.12 reachy_cli.py stop                # Linux: python3 reachy_cli.py stop
py -3.12 reachy_cli.py start
py -3.12 reachy_cli.py status
```

Or via SSH:

```bash
sudo systemctl restart treasure-hunt-reachy.service   # if install was used
# else kill the old agent and re-run /venvs/mini_daemon/bin/python agent.py …
```

### 7.4 Firewall / isolation notes

- Guest / “client isolation” hotspots often block device-to-device traffic —
  the PC will not reach `:7000`. Use a normal LAN or disable isolation.
- Re-allow the agent port if the robot firewall was reset:

```bash
sudo ufw allow 7000/tcp
```

- If you use HTTP deploy (`http.server` + `wget`), the **PC’s new IP** must be
  used in the `wget` URLs.
- Prefer a **DHCP reservation** for the robot on the new router so
  `REACHY_AGENT_HOST` stays stable.

### 7.5 Quick health after hotspot change

```powershell
curl http://insert-new-robot-ip-here:7000/health
# Open http://localhost:5000/setup and confirm Use Reachy Mini stays green
```

---

## 8. Registration / initialize ceremony — quick test

Requires: **`USE_REACHY = True` in `computer_app/config.py`** (§4.0 / §6.9),
agent healthy on `:7000`, bridge on correct `SERIAL_PORT`, hunter micro:bits
**V2** with `mb_hunter.py` flashed.

1. Start agent (if not installed as a service): `py -3.12 reachy_cli.py start`  `# Linux: python3 …`
2. Confirm config: open `computer_app/config.py` → `USE_REACHY = True`
3. Start game host:

```powershell
cd "insert path here\treasure_hunt\computer_app"
py -3.12 app.py                            # Linux: python3 app.py
```

   Host console should show something like
   `[reachy] full init ok — robot_ready=True tracker_running=True`
   (agent must already be up; otherwise init retries when you Start Game).

4. Open `http://localhost:5000/setup`
5. Set hunter/treasure counts; check **Use Reachy Mini** (health must pass)
6. **Start Game** → host calls `/init` again, then browser goes to `/initialize`
7. **Verify camera + voice:** head should track faces/motion; Reachy should
   speak the identification lines through the robot speaker
8. Each hunter: hold the **gold logo** until Reachy announces them and a
   3-button A/B code appears
9. Enter the code on the micro:bit (A/B only during ceremony)
10. Reachy confirms; hunter adopts `H#` for the session
11. When all assigned (or cancel), play proceeds to the live dashboard

Cancel path: **Cancel** on `/initialize` starts the game without binding IDs
via Reachy (manual boot-window IDs still apply if already set).

Headless protocol smoke test (no robot required for radio logic alone):

```powershell
cd "insert path here\treasure_hunt"
py -3.12 tools\simulate_registration.py    # Linux: python3 tools/simulate_registration.py
```

---

## 9. Common pitfalls

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Serial open fails / no packets | Wrong `SERIAL_PORT` | Windows: set `COMn`; Linux: `/dev/ttyACM0` + `dialout` group |
| Setup page: Reachy red / unreachable | Agent down, wrong IP, or firewall | Update `REACHY_AGENT_HOST`; `reachy_cli.py start`; `ufw allow 7000/tcp` |
| SSH hangs on Windows | QoS / OpenSSH quirk | `ssh -o IPQoS=none …` |
| `scp` deploy hangs on Windows | Known flaky path | PC `python -m http.server` + robot `wget` |
| Agent runs but no speech | Missing WAVs | Run `build_voice.py` on PC; redeploy `audio/` |
| Head never tracks faces | Old agent (no `/init`) or OpenCV missing | Redeploy agent ≥1.2; `curl …/health` should show `"tracker_running": true` after Start Game |
| SDK / import errors on robot | Wrong venv | Use `/venvs/mini_daemon/bin/python`, **not** `apps_venv` |
| Logo touch ignored | micro:bit V1 | V2 required for ceremony; use manual H# assignment |
| Works on old Wi‑Fi, fails on new hotspot | Stale IP in config | Update `config.py` + `reachy_cli.config.json`; restart agent |
| Client isolation on hotspot | Devices cannot talk | Different network / disable isolation |
| Python command not found | PATH / version | Windows: `py -3.12`; Linux: `python3` |
| Daemon not ready | Robot still booting | Wait; check `http://<robot-ip>:8000/`; `reachy_cli.py check` |

---

## Session checklist (after first-time init)

1. Bridge USB connected; `SERIAL_PORT` correct  
2. Robot powered; same Wi‑Fi as PC; agent up (`:7000/health`)  
3. **`computer_app/config.py` → `USE_REACHY = True`** (and correct `REACHY_AGENT_HOST`)  
4. `cd "insert path here\treasure_hunt\computer_app"` → `py -3.12 app.py`  `# Linux: python3 app.py`  
5. Confirm host log: full init / `tracker_running=True`; robot speaks + tracks  
6. Browser → `http://localhost:5000/setup` → check **Use Reachy Mini** → Start  

For deeper Reachy reference, see [`reachy_mini/README.md`](reachy_mini/README.md).
