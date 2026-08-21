#!/usr/bin/env python3
# build_voice.py - render a content pack's narration to WAV files, once.
#
#     python tools/build_voice.py --list
#     python tools/build_voice.py --pack dragon
#     python tools/build_voice.py                 (every pack)
#     python tools/build_voice.py --pack dragon --force
#
# WHY AHEAD OF TIME AND NOT LIVE
# The machine that runs the game may be a Raspberry Pi B+, which cannot
# synthesise speech at a usable speed but plays WAV files perfectly well. So
# this script runs ONCE on whatever computer you are authoring on, and the
# resulting files are what ship. Edit the words in packs/*.json, re-run this,
# and the session picks up the new audio with no code changes.
#
# ENGINES, in order of preference
#   1. Piper - offline neural TTS, genuinely good voices, worth the setup.
#      Get a binary and a .onnx voice from github.com/rhasspy/piper, then:
#         python tools/build_voice.py --piper C:\piper\piper.exe \
#                                     --model C:\piper\en_GB-alan-medium.onnx
#      Or drop voices in tools/voices/ named after the pack's "voice" field and
#      they will be found automatically.
#   2. pyttsx3 - pure Python, uses the OS voice. Robotic, but fine for a
#      rehearsal and arguably on-theme for the space pack.  pip install pyttsx3
#
# If neither is available the game still runs: audio.py prints each line and
# holds for about as long as reading it aloud would take, so you can rehearse a
# whole scenario silently. Nothing here is required to play.

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, os.pardir, 'computer_app'))
sys.path.insert(0, APP)

from engine import pack_lines, validate_pack       # noqa: E402

PACKS_DIR = os.path.join(APP, 'packs')
VOICE_ROOT = os.path.join(APP, 'static', 'voice')
LOCAL_VOICES = os.path.join(HERE, 'voices')


# ===========================================================================
# Engines
# ===========================================================================
def find_piper(explicit=None):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    return shutil.which('piper')


def find_model(explicit, pack):
    if explicit:
        return explicit if os.path.exists(explicit) else None

    from_env = os.environ.get('PIPER_MODEL')
    if from_env and os.path.exists(from_env):
        return from_env

    # tools/voices/<the pack's "voice" field>.onnx
    named = pack.get('voice')
    if named:
        candidate = os.path.join(LOCAL_VOICES, '{}.onnx'.format(named))
        if os.path.exists(candidate):
            return candidate

    # Otherwise any single .onnx sitting in tools/voices/
    if os.path.isdir(LOCAL_VOICES):
        found = [f for f in sorted(os.listdir(LOCAL_VOICES))
                 if f.endswith('.onnx')]
        if found:
            return os.path.join(LOCAL_VOICES, found[0])
    return None


def render_piper(piper, model, text, out_path):
    result = subprocess.run(
        [piper, '--model', model, '--output_file', out_path],
        input=text.encode('utf-8'),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode('utf-8', 'replace').strip())


def make_pyttsx3():
    try:
        import pyttsx3
    except ImportError:
        return None
    try:
        return pyttsx3.init()
    except Exception:
        return None


def render_pyttsx3(engine, text, out_path):
    engine.save_to_file(text, out_path)
    engine.runAndWait()
    if not os.path.exists(out_path):
        raise RuntimeError(
            'pyttsx3 produced no file - some OS voices cannot save to WAV')


# ===========================================================================
# Packs
# ===========================================================================
def load_pack(pack_id):
    path = os.path.join(PACKS_DIR, '{}.json'.format(pack_id))
    with open(path, encoding='utf-8') as handle:
        pack = json.load(handle)
    problems = validate_pack(pack)
    if problems:
        raise ValueError('{} is not valid:\n  {}'.format(
            path, '\n  '.join(problems)))
    return pack


def available_packs():
    return sorted(name[:-5] for name in os.listdir(PACKS_DIR)
                  if name.endswith('.json'))


def build(pack_id, piper, model_arg, force, dry_run):
    pack = load_pack(pack_id)
    lines = pack_lines(pack)
    out_dir = os.path.join(VOICE_ROOT, pack_id)

    print('\n{} - "{}"'.format(pack_id, pack.get('title', pack_id)))
    print('  {} lines -> {}'.format(len(lines), out_dir))

    if dry_run:
        for line_id, text in lines:
            exists = os.path.exists(os.path.join(out_dir, line_id + '.wav'))
            words = len(text.split())
            print('    [{}] {:<22} {:>3} words  {}'.format(
                'have' if exists else '    ', line_id, words,
                (text[:60] + '...') if len(text) > 60 else text))
        return 0, 0

    model = find_model(model_arg, pack) if piper else None
    speaker = None
    mode = None

    if piper and model:
        mode = 'piper'
        print('  engine: piper with {}'.format(os.path.basename(model)))
    else:
        speaker = make_pyttsx3()
        if speaker is not None:
            mode = 'pyttsx3'
            print('  engine: pyttsx3 (OS voice)')
            if piper and not model:
                print('  note: piper was found but no .onnx voice was;'
                      ' pass --model or drop one in tools/voices/')
        else:
            print('  no speech engine available - nothing built.')
            print('  The game still runs: lines are printed instead of spoken.')
            return 0, len(lines)

    os.makedirs(out_dir, exist_ok=True)
    built = skipped = failed = 0

    for line_id, text in lines:
        out_path = os.path.join(out_dir, '{}.wav'.format(line_id))
        if os.path.exists(out_path) and not force:
            skipped += 1
            continue
        if not text.strip():
            skipped += 1
            continue
        try:
            if mode == 'piper':
                render_piper(piper, model, text, out_path)
            else:
                render_pyttsx3(speaker, text, out_path)
            built += 1
            print('    built {}'.format(line_id))
        except Exception as exc:
            failed += 1
            print('    FAILED {}: {}'.format(line_id, exc))

    print('  {} built, {} already present, {} failed'.format(
        built, skipped, failed))
    return built, failed


def main():
    parser = argparse.ArgumentParser(
        description='Render Quest Engine narration to WAV files')
    parser.add_argument('--pack', help='pack id (default: all packs)')
    parser.add_argument('--piper', help='path to the piper executable')
    parser.add_argument('--model', help='path to a piper .onnx voice')
    parser.add_argument('--force', action='store_true',
                        help='rebuild lines that already have a WAV')
    parser.add_argument('--list', action='store_true',
                        help='show every line and whether it is built, then exit')
    opts = parser.parse_args()

    piper = find_piper(opts.piper)
    if opts.list:
        print('Narration lines. "have" means the WAV already exists.')
    elif piper:
        print('Found piper at {}'.format(piper))
    else:
        print('No piper found; will fall back to pyttsx3 if it is installed.')

    pack_ids = [opts.pack] if opts.pack else available_packs()
    total_failed = 0
    for pack_id in pack_ids:
        try:
            _, failed = build(pack_id, piper, opts.model, opts.force, opts.list)
            total_failed += failed
        except (ValueError, FileNotFoundError) as exc:
            print('\n{}: {}'.format(pack_id, exc))
            total_failed += 1

    if not opts.list:
        print('\nDone. Voices live in {}'.format(VOICE_ROOT))
    return 1 if total_failed else 0


if __name__ == '__main__':
    sys.exit(main())
