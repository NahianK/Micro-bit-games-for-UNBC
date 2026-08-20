# Treasure Hunt — micro:bit firmware

Flash these with Mu or the [micro:bit Python editor](https://python.microbit.org/).
They do **not** change when the game host moves from Windows to Linux.

| File | Role |
|------|------|
| `mb_bridge.py` | USB relay to the game host |
| `mb_treasure.py` | Field treasures (battery) |
| `mb_hunter.py` | Hunters (battery; V2 required for Reachy identification) |

On Linux / Raspberry Pi, plug the **bridge** into USB after flashing. The host
app then uses `/dev/ttyACM0` (see [`../computer_app/README.md`](../computer_app/README.md)).
