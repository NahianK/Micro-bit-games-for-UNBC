# Quest Engine — Multi-Sensor Micro:bit Quest

A screenless, audio-narrated cooperative adventure for **micro:bit V2**.

A narrator reads an instruction out loud. Every child's wand arms exactly the
sensor that instruction needs, shows progress on its LEDs, and reports back
whether the child did it and how fast. One uniform mechanic, every onboard
sensor, two swappable stories.

The children never see a screen. They get a voice, twenty-five red lights, two
beeps and a whiteboard.

```
Narrator: "Three strikes of the blade! Press A three times!"
   bridge broadcasts    C|12|BTNA|3|6000|31|0
   wands light 3 slots, fill one per press
   child finishes in 1.4 s
   wand answers         A|3|12|OK|1400|77   and chirps a rising tone
```

---

## Hardware

Six micro:bit V2 boards divide one of two ways:

| Split | Bridge | Wands | Prop | Enables |
|---|---|---|---|---|
| Five players | 1 | 5 | 0 | everything except `NEAR` |
| Four players plus a hunt | 1 | 4 | 1 | `NEAR` proximity hunting too |

Plus:

- 1 USB cable, bridge to computer. The bridge never leaves your desk.
- Battery packs (2 x AAA) for every wand and the prop.
- A computer or Raspberry Pi with **speakers the whole room can hear**.
- A whiteboard. See [`whiteboard/`](whiteboard/) for what to write on it.

Optionally, a **Reachy Mini** to be the narrator — a face for the voice and a
head that turns towards whoever is talking. It changes nothing about the game:
see [Phase 3](#phase-3-the-narrator-robot-optional).

**V2 is mandatory.** The microphone, the logo touch and the speaker do not exist
on a V1, and this game uses all three.

---

## Flashing

Always use **[python.microbit.org/v/3](https://python.microbit.org/v/3)**. Do not
use `uflash` — it installs MicroPython v1, which has radio problems on V2
hardware.

| Boards | File | Notes |
|---|---|---|
| 1 | [`microbit/mb_bridge.py`](microbit/mb_bridge.py) | stays on USB |
| 4–5 | [`microbit/mb_player.py`](microbit/mb_player.py) | one per child |
| 0–1 | [`microbit/mb_prop.py`](microbit/mb_prop.py) | optional, gets hidden |

All three use `RADIO_GROUP = 42`, matching every other game in this repo.

### Giving the wands their numbers

Every wand needs a different id or two children will share a slot.

**Wands** — on power-up the display scrolls `ID?` and you get five seconds:

- **Button A** steps the number: 1, 2, 3, 4, 5, then back to 1
- **Button B** confirms immediately
- Do nothing and it becomes **P1**

So the third wand is: power on, press A three times, press B.

**Prop** — same idea but reversed, matching Treasure Hunt so the muscle memory
carries over: **Button B** sets the number, **Button A** confirms.

---

## Phase 1: the bench test

**Do this before anything else.** It needs three boards, five minutes and no
audio, and it proves the one genuinely new piece of plumbing in this game.

Every other game in this repo is one-way: the micro:bit prints, the computer
listens. This one needs the computer to push challenges *out*, so the bridge
reads the USB serial port with `uart.read()` while still using `print()` for the
uplink. That works, but it is the thing to verify first.

```powershell
cd "D:\Cursor Repositories\quest_engine\computer_app"
pip install -r requirements.txt
python challenge_console.py --list          # find your COM port
python challenge_console.py --port COM3
```

Then:

1. **Check the uplink.** Power on a wand. Within a second or two you should see
   `[roster] P1 is online`. If not, the wand is not reaching the bridge at all —
   this is a radio or power problem, nothing to do with serial.
2. **Check the downlink.** Type `btna 3`. The wand should immediately show three
   dim dots on its top row. *This is the moment of truth: if the dots appear,
   `uart.read()` and `print()` are coexisting happily.*
3. **Check the answer path.** Press A three times. The wand shows a tick, chirps
   upwards, and the console prints something like
   `P1  done  0.84s  rssi -58`, then a verdict line.
4. **Check the timeout.** Type `btna 5` and do nothing. After the window the wand
   shows a cross, chirps downwards, and the console reports `no answer`.
5. **Walk every sensor.** Type `demo` and press Enter through the whole list.
   One clean pass exercises buttons, accelerometer gestures, logo touch,
   microphone and tilt.

### If the downlink does not work

The bridge has a **standalone mode** built in for exactly this, and it needs no
computer at all:

- **Button A** on the bridge advances through a built-in challenge list
- **Button B** repeats the current one

Everything it sends is echoed to serial, so the console still shows the answers.
A whole session can be run this way. If step 2 above fails, fall back to this,
and check `status` in the console to confirm the port is actually open.

---

## Phase 2: running a session

```powershell
cd "D:\Cursor Repositories\quest_engine\computer_app"
python app.py
```

Open `http://localhost:5000`. On a Pi, set `SERIAL_PORT = '/dev/ttyACM0'` in
`config.py` and reach it at `http://<pi-ip>:5000`.

**Turn that screen away from the children.** It is the gamemaster's instrument
panel: the whiteboard line to read out in large type, the live roster, reaction
times, the log, and buttons for Start, Pause, Skip, Force pass and Force fail.

`Force pass` matters more than it sounds. A child will sometimes obviously do the
right thing while their wand disagrees, and arguing with a sensor in front of an
audience is a losing game. Press the button and move on.

### It works before you build any audio

With no voice files, every narration line is **printed in the terminal** and the
engine pauses for about as long as reading it aloud would take. You read the
lines yourself and the pacing still holds. This is a perfectly good way to run a
first session, and the console shows a banner telling you how many lines are
unbuilt.

To build the voices:

```powershell
python tools/build_voice.py --list                    # see every line
python tools/build_voice.py --pack dragon             # render them
```

Piper gives much better voices and is worth the setup; `pyttsx3` is the pure
Python fallback. Details are in the header of
[`tools/build_voice.py`](tools/build_voice.py). Narration is rendered **once,
ahead of time**, which is why this still works on a Raspberry Pi B+ that could
never synthesise speech live.

---

## Phase 3: the narrator robot (optional)

A [Reachy Mini](https://pollen-robotics.com/reachy-mini/) can front the
narration: it speaks the same pre-rendered WAVs, nods in time with them, perks
up when a challenge opens, droops when one is failed, and turns to look at
whichever child it can see.

**It scores nothing.** Every answer still comes from a wand over radio, and no
verb, content pack or firmware file knows whether a robot is in the room. That
is the point — a robot that fails costs you an inanimate ornament, not a
session. With `USE_ROBOT = False` none of the code below runs at all.

### Install it in a virtual environment

The SDK is a large install that drags in GStreamer, MuJoCo and its own numpy.
Keep it away from the Python that runs the other games in this repo:

```powershell
cd "D:\Cursor Repositories\quest_engine"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r computer_app/requirements.txt
.\.venv\Scripts\python.exe -m pip install reachy-mini opencv-python
```

Needs Python 3.10–3.12; the SDK does not support anything newer. On Windows the
GStreamer runtime arrives with the package, so there is nothing to install by
hand.

From then on **every** command in this file runs with `.\.venv\Scripts\python.exe`
in place of `python`, the gamemaster console included — `app.py` can only see
the robot from inside the environment that holds the SDK.

### Update the robot before anything else

Check what it is running:

```powershell
curl http://reachy-mini.local:8000/api/daemon/status
```

**The version on the robot and the version of the SDK have to match.** They are
released together and the protocol between them changes. When they disagree the
SDK does not say so — it fails with a bare `Network connection attempt failed`,
which sends you hunting for a network fault that is not there.

Update at `http://reachy-mini.local:8000/settings` → Check for updates. Keep the
robot on mains power; it reboots partway through.

### Bench test it

Same reasoning as [Phase 1](#phase-1-the-bench-test): prove the new plumbing
before a room full of children depends on it. This needs no micro:bits.

```powershell
.\.venv\Scripts\python.exe tools/check_robot.py                 # connect and move
.\.venv\Scripts\python.exe tools/check_robot.py --pack dragon   # and speak a real line
.\.venv\Scripts\python.exe tools/check_robot.py --camera        # and track a face
```

It compares the two versions first and tells you plainly if they disagree, then
walks four things in the order that isolates a failure — connect, move, speak,
see. It deliberately ignores `USE_ROBOT`, because you run it to decide whether
to turn that on.

If `reachy-mini.local` does not resolve, pass `--host <ip>`. The dashboard shows
the address, or the robot's Wi-Fi settings page does.

### Turning it on

In [`computer_app/config.py`](computer_app/config.py):

| Setting | Default | What it does |
|---|---|---|
| `USE_ROBOT` | `False` | the master switch; everything else is ignored while it is off |
| `ROBOT_HOST` | `reachy-mini.local` | use the IP if that name does not resolve |
| `ROBOT_NARRATES` | `True` | narration from the robot's speaker instead of the computer's |
| `ROBOT_WOBBLE` | `True` | head moves in time with the speech |
| `ROBOT_EMOTES` | `True` | reactions when a challenge opens and when it is scored |
| `ROBOT_PRELOAD_VOICES` | `True` | send the WAVs up front rather than mid-session |
| `USE_TRACKER` | `False` | look at whoever the camera can see |

The game does not need to run *on* the robot, and should not. Wireless Reachy
Mini runs its own daemon on its onboard Pi and the SDK reaches it over Wi-Fi,
so `app.py` stays on the computer that holds the USB bridge.

### The one thing that will catch you out: volume

The hardware list at the top of this file asks for speakers the whole room can
hear, and the robot's is a companion-robot speaker about a metre from the
children rather than a PA across the hall.

Worse, it moves the narration *towards* the wands' microphones, so the
threshold work in [Tuning](#microphone--do-this-first-it-is-the-most-likely-to-disappoint)
has to be redone against it. `python tools/check_robot.py --pack dragon` plays
a real line so you can judge this before committing to it.

If it is too quiet, set `ROBOT_NARRATES = False`. The PA keeps the narration and
the robot still moves, reacts and watches the room — which is most of what it
was for.

### What the camera does, and what it does not

`USE_TRACKER = True` makes the robot look at people. That is the whole feature.
It scores nothing, and there is a reason it stops there.

The wire protocol is per-player — `A|<pid>|<result>|<ms>` — and a face is not a
player id. To score "player 3 waved" something has to map a body in the image
to a wand number, and the camera cannot do that alone. Two ways out, neither
built:

- **Numbered floor spots.** Children stand in fixed places and image zones map
  to player ids. Cheap and robust, but the head must be held still during the
  answer window, because the camera is mounted *in* the head and every look
  invalidates the mapping.
- **Group verbs.** Something like "everybody freeze" is scored across the whole
  frame and needs no attribution at all. This is the easier of the two and the
  better place to start.

That camera-in-the-head problem shapes the tracker as it stands, too: it
ignores frames for `TRACKER_SETTLE_S` after each move, and only falls back to
motion detection once the head has been still, because to a moving camera every
pixel in the room is moving.

### Limits worth knowing

| Limit | Consequence |
|---|---|
| the SDK and the robot's software must match | update the robot whenever you upgrade the pip package, and vice versa |
| `play_sound` cannot be interrupted | the gamemaster's stop button takes effect at the end of the current sentence, not instantly |
| nothing reports when playback ends | line length is read from the WAV header and waited out, so a hand-edited WAV with a wrong header will drift the pacing |
| the first play of a file uploads it | leave `ROBOT_PRELOAD_VOICES = True` or the first airing of every line stalls |
| servos are audible | the robot freezes during `CLAP` and `SHOUT` windows, which is why it goes briefly inert there |

---

## The verb vocabulary

The whole game is built from these. `arg` means something different per verb.

| Verb | Sensor | `arg` | The move |
|---|---|---|---|
| `BTNA` `BTNB` | buttons | count | press that button n times |
| `BTNAB` | buttons | — | press both together |
| `TILTL` `TILTR` `TILTU` `TILTD` | accelerometer | count | tilt that way |
| `SHAKE` | accelerometer | count | shake it |
| `FACEUP` `FACEDN` | accelerometer | — | turn it over |
| `CLAP` | microphone | count | n distinct claps |
| `SHOUT` | microphone | ms | sustain a shout |
| `HOLD` | logo touch | ms | hold the gold logo |
| `LEVEL` | accelerometer | ms | hold it flat and still |
| `POINT` | compass | bearing | point to a bearing |
| `NEAR` | radio RSSI | — | walk to the hidden prop |
| `IDLE` | — | — | stand down |

---

## Wire protocol

Four message shapes, all well under the 32-byte radio payload. The longest
command this game generates is 21 characters.

| Message | Direction | Shape |
|---|---|---|
| Command | bridge to wands | `C\|<seq>\|<verb>\|<arg>\|<win>\|<mask>\|<ack>` |
| Answer | wand to bridge | `A\|<pid>\|<seq>\|<result>\|<ms>\|<eid>` |
| Heartbeat | wand to bridge | `H\|<pid>\|<seq>\|<flags>` |
| Beacon | prop to wands | `B\|<prop_id>` |

The bridge relays everything to USB as `<payload>,<rssi>`. Its own echoes carry
**no** trailing comma, which is how the computer tells "I sent this" apart from
"I overheard this".

### The acknowledgement trick

Micro:bit radio is fire-and-forget with no ACKs, which the other games in this
repo work around by simply broadcasting often and hoping. This game does better
without adding a single extra packet type.

The computer sends each command down the serial port **once**. The bridge stores
it and rebroadcasts every 250 ms, and as answers arrive it sets each answering
player's bit in the `ack` field of those repeats. A wand keeps resending its
answer only while its own bit is still clear, and goes quiet the moment it sees
itself acknowledged.

So the repeated command doubles as the acknowledgement channel. Nothing is lost
silently, nobody floods the airwaves, and the retry loop stays on the radio
where latency is low instead of going out to the computer and back.

`mask` is a player bitmask, which is how the narrator calls out one child by
name while the other four wands show "not your turn".

`computer_app/protocol.py` is the source of truth for these shapes. MicroPython
cannot import it, so the firmware builds the same strings by hand — **if you
change one, change both.**

---

## Tuning

Everything below needs real hardware, a real room and ideally real children.
Nothing in the simulators can settle any of it.

### Microphone — do this first, it is the most likely to disappoint

The wands hear your PA. If narration registers as clapping, the whole game
misbehaves in a way that looks like a bug.

In [`microbit/mb_player.py`](microbit/mb_player.py):

| Constant | Default | Raise it if | Lower it if |
|---|---|---|---|
| `LOUD_THRESHOLD` | 150 | narration counts as claps | real claps are missed |
| `SHOUT_LEVEL` | 140 | shouting passes too easily | children shout and nothing happens |
| `CLAP_DEBOUNCE_MS` | 250 | one clap counts twice | fast double claps merge into one |
| `MIC_MUTE_MS` | 400 | the wand's own chirp counts as a clap | claps right after a chirp are missed |

Method: start `challenge_console.py`, play narration through the PA at the volume
you will actually use, and type `clap 2`. If it passes without anybody clapping,
raise `LOUD_THRESHOLD` by 30 and re-flash. Repeat until only real claps register.

The engine already goes silent for `MIC_QUIET_LEAD_S` before opening any
microphone challenge, so you are tuning against the room, not against the
narrator.

If you are using a [robot narrator](#phase-3-the-narrator-robot-optional), tune
against **that** speaker rather than the PA, and re-tune if you ever switch
between them. It sits far closer to the wands, so the same `LOUD_THRESHOLD` will
not serve both.

### Tilt directions

`'left'` and `'right'` are defined against the **board's** axes, not against the
child's body. Verify before printing the whiteboard chart — the procedure is in
[`whiteboard/gesture_chart.md`](whiteboard/gesture_chart.md). If they feel
backwards, swap the entries in `GESTURE_FOR`.

### Level

`LEVEL_TOL` is 250 milli-g. Raise it for younger children; lower it to make
carrying the cauldron genuinely tense.

### Compass — off by default

`POINT` challenges are disabled, and deliberately. To enable them you need
**both**:

1. `USE_COMPASS = True` in `microbit/mb_player.py`
2. `USE_COMPASS = True` in `computer_app/config.py`

Then every wand runs a blocking 20–40 second calibration game at boot,
**in the room you will play in**. Steel and rebar bend the readings badly.

The two flags are separate on purpose. The firmware one turns on calibration; the
config one lets the engine know it is allowed to run `POINT` steps. With the
config flag off, any step declaring `"requires": "compass"` is **skipped with a
log line** rather than handed to children who cannot possibly answer it.

If a wand is asked for a bearing while uncalibrated it replies `NOCAL` rather
than `FAIL`, and the console shows "no compass", so a screenful of instant
failures is never mistaken for a bug.

Read the warnings in [`whiteboard/compass_rose.md`](whiteboard/compass_rose.md)
before planning a session around bearings. A `TILTL` challenge plays almost
identically to a child and always works.

### Proximity, for `NEAR`

Set `USE_PROP = True` in `config.py` and calibrate as in the other games:

| Constant | Meaning |
|---|---|
| `RSSI_HOT` | close enough to count as found |
| `RSSI_FLOOR` | one-LED range, the edge of the hunt |

Reference indoor readings are in the repo root README. Recalibrate every
session — hiding places change, and indoor RSSI swings 10–15 dBm from
reflections alone.

---

## Writing your own scenario

Copy [`computer_app/packs/dragon.json`](computer_app/packs/dragon.json) and
replace the text. The two shipped packs are step-for-step mirrors of each other,
which is the proof that the engine is theme-neutral: same verbs, same order,
completely different story.

Per step:

| Field | Meaning |
|---|---|
| `id` | unique, lowercase, also the WAV filename |
| `type` | `say` or `challenge` |
| `verb`, `arg`, `win` | the challenge itself; `win` defaults per verb |
| `say` | read aloud before the challenge opens |
| `on_pass`, `on_fail` | read aloud afterwards |
| `say_again` | used on a retry, with `attempts` |
| `require` | `all`, `any`, `majority`, or a number |
| `who` | `all`, `random`, or a list like `[1, 3]` |
| `whiteboard` | the short version, shown big to the gamemaster |
| `requires` | `compass` or `prop`; skipped unless enabled |
| `sfx`, `sfx_pass`, `sfx_fail` | names of WAVs in `static/sfx/` |

A broken pack is **refused at load** with a list of problems, rather than
failing halfway through a session. After editing text, re-run
`tools/build_voice.py`.

Difficulty scales every window globally via `DIFFICULTY_WINDOW_SCALE` in
`config.py` — easy gives 1.5x the time, hard gives 0.65x — so packs do not need
their own difficulty tiers.

---

## Testing without hardware

Three simulators, all of which run the **real** code rather than a copy:

```powershell
python tools/simulate_wand.py        # 47 checks on the wand firmware
python tools/simulate_session.py     # plays both packs with fake wands
python tools/simulate_robot.py       # 48 checks on the robot, with no robot
```

`simulate_wand.py` stubs the micro:bit API and executes
`microbit/mb_player.py` up to its main loop, then drives `tick()` by hand. It
covers the traps: counting, window expiry, stale gestures being flushed on arm,
clap debounce, the wand not hearing its own chirp, holds restarting on release,
compass wraparound across the 0/360 seam, the acknowledge handshake, and
surviving corrupt packets.

`simulate_session.py` wires the real engine to a fake transport whose wands
answer themselves. Run it after editing a pack.

`simulate_robot.py` stubs the Reachy Mini SDK and OpenCV, then drives the real
`robot.py` and `tracker.py`. It matters because the robot has a long lead time
and lives on a network, so without it the narration routing and the tracker's
aiming rules would go untested until the day they are needed. It covers the
upload-once cache, `say()` blocking for the length of a line, microphone
challenges freezing the head, and the tracker leaving a centred face alone.

None of them prove anything physical — not radio range, not microphone
thresholds, not whether the robot is loud enough, not whether a child
understands "tilt left". They prove the bookkeeping.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Console says no bridge | wrong port, or another program holds it | `python challenge_console.py --list`; close other Python processes |
| Wand never appears in the roster | radio group mismatch or flat battery | confirm `RADIO_GROUP = 42` everywhere |
| Wand ignores challenges but heartbeats fine | downlink not reaching the bridge | see "if the downlink does not work" above; use bridge Button A |
| Two children share a wand number | both defaulted to P1 | re-power and assign ids with Button A |
| Narration counts as clapping | `LOUD_THRESHOLD` too low | raise it by 30 and re-flash |
| Claps counted twice | echo inside the debounce | raise `CLAP_DEBOUNCE_MS` |
| Everyone fails `POINT` instantly, console says "no compass" | compass not calibrated | enable both `USE_COMPASS` flags, or skip the step |
| Every `NEAR` step is skipped | `USE_PROP` is False | set it True and flash `mb_prop.py` |
| Sad face on a micro:bit | wrong MicroPython version | re-flash via python.microbit.org/v/3 |
| Wand LEDs freeze | a blocking call, almost certainly `compass.heading()` uncalibrated | the firmware guards this; re-flash the current file |
| Narration silent, terminal printing lines | pygame missing, or no voices built | `pip install pygame`, then `tools/build_voice.py` |
| Console says no robot | wrong host, or the robot is not awake | `.\.venv\Scripts\python.exe tools/check_robot.py --host <ip>` |
| `Network connection attempt failed`, but the robot pings fine | the robot's software and the SDK are different versions | update at `reachy-mini.local:8000/settings`; `check_robot.py` names both versions |
| `ModuleNotFoundError: reachy_mini` when running `app.py` | started outside the venv | use `.\.venv\Scripts\python.exe app.py` |
| Robot connects but never speaks | `ROBOT_NARRATES` is False, or the voices are not built | check the robot pill in the console; build the voices |
| A pause the first time each line is spoken | `ROBOT_PRELOAD_VOICES` is False, so every line uploads on demand | set it True |
| Robot narration counts as clapping | the robot's speaker is much closer to the wands than a PA | re-tune `LOUD_THRESHOLD` against the robot, not the PA |
| Robot drifts slowly off across the room | it is tracking its own movement | raise `TRACKER_SETTLE_S`, and `TRACKER_DEADZONE_PX` if it also twitches |
| Robot ignores the children | too dark for the face detector, or nobody is facing it | more light; it falls back to movement, which needs the head still |
| Robot upstages the narrator | too much head movement for the room | `action: tracking, value: off` from the console, or `ROBOT_EMOTES = False` |

---

## Files

```
quest_engine/
├── microbit/
│   ├── mb_bridge.py          two-way relay, repeat + ack, standalone mode
│   ├── mb_player.py          the wand: all sensors, challenge state machine
│   └── mb_prop.py            optional hidden beacon for NEAR
├── computer_app/
│   ├── challenge_console.py  Phase 1 bench harness (only needs pyserial)
│   ├── app.py                gamemaster web console
│   ├── engine.py             scenario state machine, scoring, pack validation
│   ├── protocol.py           wire format, single source of truth
│   ├── audio.py              WAV playback, ducking, silent fallback
│   ├── robot.py              optional Reachy Mini: voice, reactions, gaze
│   ├── tracker.py            optional camera presence tracking
│   ├── config.py             port, thresholds, optional hardware flags
│   ├── transports/           base.py + serial_bridge.py (BLE slot here)
│   ├── packs/                dragon.json, space.json
│   ├── templates/gm.html     the console
│   └── static/gm.js          console client
├── tools/
│   ├── simulate_wand.py      run the firmware logic on a PC
│   ├── simulate_session.py   play a pack with fake wands
│   ├── simulate_robot.py     run the robot code with no robot
│   ├── check_robot.py        Phase 3 bench test for the Reachy Mini
│   └── build_voice.py        render narration to WAV, once
└── whiteboard/               what to write up for the children
```

---

## Why not Bluetooth

The obvious idea is to skip the bridge and have all six boards talk straight to
the computer over their onboard Bluetooth. It does not work, for two independent
reasons, and both are worth recording so nobody spends a weekend on it.

**MicroPython has no BLE.** The
[official docs](https://microbit-micropython.readthedocs.io/en/v2-docs/ble.html)
state that on V2 "the only implemented feature is BLE flashing". The Bluetooth
stack sits in flash for the bootloader and is not exposed to Python at all.

**Bluetooth and radio are mutually exclusive on the hardware**, in every
language. MakeCode deletes the radio extension when you add Bluetooth.

That second point costs more than it first appears. Every proximity mechanic in
this repo works because one micro:bit *hears another micro:bit* and reads the
signal strength. Over BLE the boards cannot hear each other at all — the stack
cannot act as a BLE central, only a peripheral — so the only distance measurable
would be each board's distance to the computer. `NEAR` would be impossible, and
so would Hide and Seek and Treasure Hunt.

Going BLE would also mean rewriting everything in MakeCode, whose "Python" is a
different language from MicroPython, so none of these files would carry over.

The two-way bridge gets the thing BLE was wanted for — a downlink so the
computer can drive the story — while keeping peer-to-peer RSSI and every line of
existing code.

---

## Next steps

- Run the Phase 1 bench test and tune `LOUD_THRESHOLD` against whichever
  speaker will actually narrate.
- Verify the tilt directions and finalise the whiteboard chart.
- Download Piper `.onnx` models into `tools/voices/` (see that folder's README),
  build narration with `tools/build_voice.py`, and record a dragon roar and an
  alarm into `computer_app/static/sfx/`.
- Run the Phase 3 bench test once the Reachy Mini arrives, and settle the
  volume question before planning a session around it.
- **Team mode** (split teams / team scoring) is not in this tree — only
  cooperative single-group play. Add it later if a session design needs it.
- Camera-scored challenges, if the presence tracking earns its keep: start with
  group verbs that need no per-child attribution, and add a transport that
  emits answers so no trial logic, pack or audio has to change — that is the
  whole reason the transport layer exists.
