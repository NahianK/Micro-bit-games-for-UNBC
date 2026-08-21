#!/usr/bin/env python3
"""Generate 1-10 speech on Windows and play it on Reachy Mini."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

HOST = "10.38.22.140"
BASE = f"http://{HOST}:8000"
FILENAME = "count_1_to_10.wav"


def http(method, path, data=None, headers=None, timeout=30):
    req = urllib.request.Request(
        BASE + path, data=data, method=method, headers=headers or {}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def synthesize_wav(out_path):
    # Windows SAPI via PowerShell — no extra Python packages needed.
    ps = r"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = -2
$synth.Volume = 100
$synth.SetOutputToWaveFile('{out}')
$synth.Speak('One. Two. Three. Four. Five. Six. Seven. Eight. Nine. Ten.')
$synth.Dispose()
""".format(out=out_path.replace("'", "''"))
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout or "TTS failed")
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        raise RuntimeError("TTS produced no usable WAV")


def wav_seconds(path):
    with wave.open(path, "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def upload(path):
    boundary = "----reachycount"
    with open(path, "rb") as handle:
        file_data = handle.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{FILENAME}"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    status, resp = http(
        "POST",
        "/api/media/sounds/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    print("upload", status, resp.decode("utf-8", "replace"))
    if status >= 400:
        raise RuntimeError("upload failed")


def play():
    status, resp = http(
        "POST",
        "/api/media/play_sound",
        data=json.dumps({"file": FILENAME}).encode(),
        headers={"Content-Type": "application/json"},
    )
    print("play", status, resp.decode("utf-8", "replace"))
    if status >= 400:
        raise RuntimeError("play failed")


def main():
    print("Checking robot...", BASE)
    status_body = urllib.request.urlopen(f"{BASE}/api/daemon/status", timeout=5).read()
    print(status_body.decode()[:200])
    media = urllib.request.urlopen(f"{BASE}/api/media/status", timeout=5).read()
    print("media", media.decode())

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, FILENAME)
        print("Synthesizing 1-10...")
        synthesize_wav(path)
        seconds = wav_seconds(path)
        print(f"WAV ready ({seconds:.1f}s, {os.path.getsize(path)} bytes)")
        upload(path)
        print("Playing on Reachy Mini speaker...")
        play()
        time.sleep(seconds + 0.5)
    print("Done. You should have heard one through ten.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        print("Robot unreachable:", exc, file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print("Failed:", exc, file=sys.stderr)
        sys.exit(1)
