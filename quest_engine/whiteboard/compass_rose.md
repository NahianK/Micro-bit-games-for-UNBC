# The Compass Rose

Only needed if you run `POINT` challenges. Those are **off by default** — see
the compass section of the README before you plan a session around them.

---

## Write this on the board

Draw it in the corner of the board and, crucially, **rotate it to match the
actual room** so that the N on the board points the same way as north does.
Children navigate by landmarks, not by abstractions.

```
                 N
                 |
        NW       |       NE
           \     |     /
             \   |   /
               \ | /
    W -----------+----------- E
               / | \
             /   |   \
           /     |     \
        SW       |       SE
                 |
                 S
```

Then label it with things they can see:

```
   N  = towards the WINDOWS
   E  = towards the DOOR
   S  = towards the STAGE
   W  = towards the STORE CUPBOARD
```

Fill those in on the day. A child will find "point at the windows" instantly and
"point north-east" not at all.

---

## Bearings the packs use

| Name | Degrees |
|---|---|
| N | 0 |
| NE | 45 |
| E | 90 |
| SE | 135 |
| S | 180 |
| SW | 225 |
| W | 270 |
| NW | 315 |

A wand accepts anything within **25 degrees** of the target and the child has to
hold it there for about a second. That tolerance is deliberately generous: it is
roughly "the right side of the room", not "the right spot on the wall".

---

## Why this is the least reliable part of the game

Be warned before you build a session around it.

- **Steel distorts it.** Reinforced concrete floors, radiators, metal-framed
  tables and door frames all bend the reading. A wand can be confidently wrong
  by 40 degrees while standing next to a filing cabinet, and children will not
  understand why they are failing.
- **Calibration is per board and it is slow.** `compass.calibrate()` is a
  blocking tilt-the-board game taking 20 to 40 seconds. Five wands is around
  three minutes of children standing still doing nothing.
- **Calibrate in the room you will play in.** A calibration from the office does
  not transfer to the hall.
- **The wand's own speaker interferes.** The V2 speaker sits near the
  magnetometer and its magnet skews readings, which is why the firmware never
  beeps during a bearing hold, only after it.

If a bearing challenge misbehaves on the day, hit **Skip step** on the
gamemaster console and carry on. Better still, substitute a `TILTL` or `TILTR`
challenge: "the sound is coming from your left" plays almost identically to a
child and is completely reliable.
