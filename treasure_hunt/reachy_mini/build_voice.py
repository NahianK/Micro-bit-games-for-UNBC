#!/usr/bin/env python3
# build_voice.py — render Treasure Hunt narration to WAV files.
#
# Run this ONCE on the authoring machine, then deploy the resulting audio/
# folder to the robot (reachy_cli.py deploy will copy it).
#
# USAGE
#   python build_voice.py                            # uses auto-discovered Piper/pyttsx3
#   python build_voice.py --piper C:\piper\piper.exe
#   python build_voice.py --model C:\piper\voices\en_US-amy-medium.onnx
#   python build_voice.py --force                    # rebuild all (skip existing)
#   python build_voice.py --list                     # print all line IDs
#
# VOICE MODEL
#   The American female voice used here is en_US-amy-medium from Piper.
#   Download the model (two files) from:
#     https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/amy/medium
#   Save both .onnx and .onnx.json files, then pass --model or put them in:
#     quest_engine/tools/voices/en_US-amy-medium.onnx
#
#   Piper binary: https://github.com/rhasspy/piper/releases
#   (piper.exe for Windows, piper for Linux/macOS/Pi)
#
# FALLBACK
#   If Piper is not found, the script tries pyttsx3 (pip install pyttsx3).
#   The quality is robotic but serviceable for testing.
#
# The runtime agent never synthesises — it only plays WAVs.

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(HERE, 'audio')
LINES_FILE = os.path.join(HERE, 'audio', 'voice_lines.json')
QUEST_VOICES = os.path.abspath(
    os.path.join(HERE, '..', '..', 'quest_engine', 'tools', 'voices'))

TARGET_VOICE = 'en_US-amy-medium'


# ---------------------------------------------------------------------------
# Line loading
# ---------------------------------------------------------------------------

def load_all_lines():
    """Return {id: text} for every line and fragment."""
    with open(LINES_FILE, encoding='utf-8') as f:
        data = json.load(f)
    lines = {}
    for item in data.get('lines', []):
        lines[item['id']] = item['text']
    for item in data.get('fragments', []):
        lines[item['id']] = item['text']
    return lines


# ---------------------------------------------------------------------------
# Piper
# ---------------------------------------------------------------------------

def find_piper(explicit=None):
    if explicit and os.path.exists(explicit):
        return explicit
    return shutil.which('piper') or shutil.which('piper.exe')


def find_model(explicit=None):
    if explicit and os.path.exists(explicit):
        return explicit

    # quest_engine voices folder
    candidate = os.path.join(QUEST_VOICES, '{}.onnx'.format(TARGET_VOICE))
    if os.path.exists(candidate):
        return candidate

    # Any .onnx in QUEST_VOICES that is en_US
    if os.path.isdir(QUEST_VOICES):
        for f in sorted(os.listdir(QUEST_VOICES)):
            if f.endswith('.onnx') and 'en_US' in f:
                return os.path.join(QUEST_VOICES, f)

    return None


def render_piper(piper_bin, model_path, text, out_path):
    cmd = [piper_bin, '--model', model_path,
           '--output_file', out_path, '--quiet']
    result = subprocess.run(
        cmd, input=text.encode(), capture_output=True, timeout=30)
    return result.returncode == 0 and os.path.exists(out_path)


# ---------------------------------------------------------------------------
# pyttsx3 fallback
# ---------------------------------------------------------------------------

def render_pyttsx3(text, out_path):
    try:
        import pyttsx3
    except ImportError:
        return False
    try:
        engine = pyttsx3.init()
        engine.save_to_file(text, out_path)
        engine.runAndWait()
        return os.path.exists(out_path)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Build Treasure Hunt narration WAVs')
    parser.add_argument('--piper',  help='Piper binary path')
    parser.add_argument('--model',  help='Piper .onnx voice model path')
    parser.add_argument('--force',  action='store_true',
                        help='Re-render WAVs that already exist')
    parser.add_argument('--list',   action='store_true',
                        help='Print all line IDs and exit')
    args = parser.parse_args()

    lines = load_all_lines()

    if args.list:
        for lid, text in sorted(lines.items()):
            print('{:<25} {}'.format(lid, text[:70]))
        return

    os.makedirs(AUDIO_DIR, exist_ok=True)

    piper = find_piper(args.piper)
    model = find_model(args.model) if piper else None

    if piper and model:
        print('Engine : Piper ({})'.format(os.path.basename(model)))
    elif piper:
        print('Piper found but no model. Pass --model or download en_US-amy-medium.')
        print('See: https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/amy/medium')
        piper = None

    if not piper:
        try:
            import pyttsx3
            print('Engine : pyttsx3 (fallback — robotic quality)')
        except ImportError:
            print('ERROR: no TTS engine found.')
            print('Option A: download Piper + en_US-amy-medium model (recommended)')
            print('Option B: pip install pyttsx3')
            sys.exit(1)

    built = skipped = failed = 0
    t0 = time.time()

    for lid, text in sorted(lines.items()):
        out = os.path.join(AUDIO_DIR, '{}.wav'.format(lid))
        if os.path.exists(out) and not args.force:
            skipped += 1
            continue

        ok = False
        if piper and model:
            ok = render_piper(piper, model, text, out)
        if not ok:
            ok = render_pyttsx3(text, out)

        if ok:
            built += 1
            print('  OK  {}'.format(lid))
        else:
            failed += 1
            print('  FAIL {}'.format(lid))

    elapsed = time.time() - t0
    print('\nDone — built={} skipped={} failed={} ({:.1f}s)'.format(
        built, skipped, failed, elapsed))
    if built or skipped:
        print('Deploy with: python reachy_cli.py deploy')


if __name__ == '__main__':
    main()
