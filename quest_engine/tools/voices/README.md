# Piper voice models (not in git)

Drop the matching `.onnx` files here before running `tools/build_voice.py`.
The `.onnx.json` sidecars in this folder name the models the packs expect.

| Pack | Model id | Typical download |
|---|---|---|
| `dragon` | `en_GB-cori-high` | [rhasspy/piper voices](https://github.com/rhasspy/piper/blob/master/VOICES.md) |
| `space` | `en_US-amy-medium` | same |

Also useful for tests: `en_GB-alan-medium`.

**Why they are not committed:** neural voice models are tens to 100+ MB each.
GitHub rejects files over 100 MB (`en_GB-cori-high.onnx` is over that limit), and
shipping them would bloat the repo. Install [Piper](https://github.com/rhasspy/piper)
locally (this monorepo often keeps a Windows build under `piper/` at the root —
that folder is gitignored too), then:

```powershell
# from quest_engine/
python tools/build_voice.py --piper ..\piper\piper.exe --pack dragon
python tools/build_voice.py --piper ..\piper\piper.exe --pack space
```

Without models, the game still runs: narration prints in the terminal with timed
pauses (see the quest_engine README).
