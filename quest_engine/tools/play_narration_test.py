#!/usr/bin/env python3
"""Generate a short narration with Windows SAPI and play it on Reachy Mini."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = os.path.join(HERE, "voices", "en_GB-cori-high.onnx")
DEFAULT_TEXT = (
    "Welcome, adventurers. Your quest is about to begin. "
    "Ready your wands, listen carefully, and work together!"
)


def request(base, method, path, data=None, headers=None):
    req = urllib.request.Request(
        base + path, data=data, method=method, headers=headers or {}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.status, response.read()


def synthesize(path, text, model):
    if model and os.path.exists(model):
        piper = os.path.join(os.path.dirname(sys.executable), "piper.exe")
        result = subprocess.run(
            [piper, "--model", model, "--output_file", path],
            input=text.encode("utf-8"),
            capture_output=True,
        )
        if result.returncode:
            raise RuntimeError(
                result.stderr.decode("utf-8", "replace")
                or "Piper speech synthesis failed"
            )
        return "Piper neural voice"

    script = """
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = -1
$synth.Volume = 100
$synth.SetOutputToWaveFile('{path}')
$synth.Speak('{text}')
$synth.Dispose()
""".format(
        path=path.replace("'", "''"),
        text=text.replace("'", "''"),
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr or "Windows speech synthesis failed")
    return "Windows SAPI fallback"


def upload(base, path, filename):
    boundary = "----reachynarration"
    with open(path, "rb") as audio_file:
        audio = audio_file.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode() + audio + f"\r\n--{boundary}--\r\n".encode()
    return request(
        base,
        "POST",
        "/api/media/sounds/upload",
        body,
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="reachy-mini.local")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    base = f"http://{args.host}:8000"
    filename = "quest_narration_test.wav"
    status = json.loads(request(base, "GET", "/api/daemon/status")[1])
    volume = json.loads(request(base, "GET", "/api/volume/current")[1])
    print(
        f"Robot {status['version']} is {status['state']}; "
        f"speaker volume is {volume['volume']}."
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        wav_path = os.path.join(temp_dir, filename)
        engine = synthesize(wav_path, args.text, args.model)
        with wave.open(wav_path, "rb") as wav:
            duration = wav.getnframes() / float(wav.getframerate())

        upload_status, _ = upload(base, wav_path, filename)
        play_status, _ = request(
            base,
            "POST",
            "/api/media/play_sound",
            json.dumps({"file": filename}).encode(),
            {"Content-Type": "application/json"},
        )
        print(
            f"{engine}; upload {upload_status}; playback {play_status}; "
            f"duration {duration:.1f}s."
        )
        time.sleep(duration + 0.5)


if __name__ == "__main__":
    main()
