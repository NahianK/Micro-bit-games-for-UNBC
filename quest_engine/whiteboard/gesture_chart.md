# The Moves

**Copy this onto the whiteboard before the children arrive.**
This is the only reference they get, so keep it big and keep it up all session.

Write the middle column only. The right-hand columns are for you.

---

## Write this on the board

```
        THE MOVES

  PRESS A          the left button
  PRESS B          the right button
  BOTH             both buttons at once

  TILT LEFT        lean it left
  TILT RIGHT       lean it right
  TILT UP          lean the top away from you
  TILT DOWN        lean the top towards you

  SHAKE            shake it hard
  FACE DOWN        turn the lights to the floor
  FACE UP          turn the lights to the ceiling

  HOLD THE LOGO    thumb on the gold oval, keep it there
  CLAP             one sharp clap
  SHOUT            shout and KEEP shouting

  FLAT AND STILL   hold it level, do not wobble
```

---

## Gamemaster crib sheet

| On the board | Verb | Dragon words | Space words |
|---|---|---|---|
| PRESS A | `BTNA` | strike your shield | tap your chest console |
| PRESS B | `BTNB` | sound your horn | send the ready signal |
| BOTH | `BTNAB` | two hands on the hilt | both hands on the lever |
| TILT LEFT | `TILTL` | the trail bends left | vent to port |
| TILT RIGHT | `TILTR` | the trail bends right | vent to starboard |
| TILT UP | `TILTU` | raise your point | pitch up |
| TILT DOWN | `TILTD` | drop your point | pitch down |
| SHAKE | `SHAKE` | strike! / shake them off | turn the crank / shake them off |
| FACE DOWN | `FACEDN` | shields up | shields down over your visor |
| FACE UP | `FACEUP` | blade to the sky | open the upper hatch |
| HOLD THE LOGO | `HOLD` | grip the rune | palm on the contact |
| CLAP | `CLAP` | the war cry | sonic pulse |
| SHOUT | `SHOUT` | bellow back at it | shout over the interference |
| FLAT AND STILL | `LEVEL` | carry the cauldron | carry the canister |
| POINT NORTH-EAST | `POINT` | the roar comes from... | align the dish to... |
| HUNT THE LIGHTS | `NEAR` | find the hoard | find the flight recorder |

---

## Before you print this, verify the tilts

The micro:bit decides what "left" means using the **board's own axes**, and that
may not match how a child is holding it. It costs two minutes to check and it
saves an entire session of confusion:

1. Flash a wand and start `challenge_console.py`.
2. Type `tiltl` and tilt the board the way a child naturally would for "left".
3. If nothing registers, swap `TILT LEFT` and `TILT RIGHT` on the board — or
   swap the `'left'` and `'right'` entries in `GESTURE_FOR` in
   `microbit/mb_player.py`, which fixes it everywhere at once.

Do the same for up and down. `TILTU`/`TILTD` are the likeliest pair to feel
backwards, because whether "up" means the top edge lifting or the whole board
tipping away depends entirely on how the wand is held.

---

## Things worth saying out loud at the start

- Your wand talks to you with **lights and beeps**. Nothing else.
- A **rising beep** means it worked. A **falling beep** means it did not.
- If your lights go dim and small, **it is not your turn** — wait.
- Nobody is out. A missed move just means the story gets harder.
