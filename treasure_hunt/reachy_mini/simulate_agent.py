#!/usr/bin/env python3
# simulate_agent.py — smoke-test the agent without a robot.
#
# Stubs the reachy_mini SDK and OpenCV, then starts the full agent stack in
# the same process and sends representative HTTP events. Run before deploying
# to the real robot.
#
#   python simulate_agent.py
#   python simulate_agent.py --port 7001   # if 7000 is busy

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import urllib.request
import wave
import struct

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Fake reachy_mini SDK
# ---------------------------------------------------------------------------

class _FakeAudio:
    def __init__(self):
        self.played = []
    def upload_sound(self, path):
        pass
    def play_sound(self, name):
        self.played.append(name)
    def stop_playing(self):
        pass
    def get_frame(self):
        return None

class _FakeCamera:
    resolution = (640, 480)

class _FakeMedia:
    def __init__(self):
        self.audio = _FakeAudio()
        self.camera = _FakeCamera()
    def play_sound(self, name):
        self.audio.play_sound(name)
    def stop_playing(self):
        self.audio.stop_playing()
    def get_frame(self):
        return None

class _FakeMini:
    def __init__(self, **kwargs):
        self.media = _FakeMedia()
        self._wobbling = False
    def wake_up(self): pass
    def enable_wobbling(self): self._wobbling = True
    def goto_target(self, **kwargs): pass
    def look_at_image(self, u, v, duration=0.5): pass
    def goto_sleep(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass

class _FakeUtils:
    @staticmethod
    def create_head_pose(mm=False, degrees=False, **kwargs):
        return kwargs

_fake_module = types.ModuleType('reachy_mini')
_fake_module.ReachyMini = _FakeMini

_fake_utils = types.ModuleType('reachy_mini.utils')
_fake_utils.create_head_pose = _FakeUtils.create_head_pose

sys.modules.setdefault('reachy_mini', _fake_module)
sys.modules.setdefault('reachy_mini.utils', _fake_utils)

_fake_np = types.ModuleType('numpy')
_fake_np.deg2rad = lambda x: x
sys.modules.setdefault('numpy', _fake_np)

# Stub cv2
_fake_cv2 = types.ModuleType('cv2')
sys.modules.setdefault('cv2', _fake_cv2)

# ---------------------------------------------------------------------------
# Tiny 1-second silent WAV for testing
# ---------------------------------------------------------------------------

def _make_silent_wav(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sample_rate = 16000
    duration_s = 0.1
    n_frames = int(sample_rate * duration_s)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack('<{}h'.format(n_frames), *([0] * n_frames)))


WAV_IDS = [
    'init_open', 'init_missing_1', 'init_all_ready',
    'init_confirm_1', 'init_confirm_2', 'init_retry', 'init_complete', 'init_cancel',
    'game_start', 'game_over', 'winner_1', 'winner_tie',
    'claim_pre', 'claim_post', 'found_pre', 'found_post_T1',
    'hunter_1', 'hunter_2', 'code_ABA',
]

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _post(url, body, token=''):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={'Content-Type': 'application/json',
                 'Content-Length': str(len(data))})
    if token:
        req.add_header('Authorization', 'Bearer {}'.format(token))
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())

def _get(url, token=''):
    req = urllib.request.Request(url)
    if token:
        req.add_header('Authorization', 'Bearer {}'.format(token))
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())

# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

PASS = []
FAIL = []

def check(label, cond, detail=''):
    if cond:
        print('  PASS  {}'.format(label))
        PASS.append(label)
    else:
        print('  FAIL  {} {}'.format(label, detail))
        FAIL.append(label)

def section(title):
    print('\n{}'.format(title))
    print('-' * len(title))

def run_tests(base_url, token=''):
    section('1. Health check')
    h = _get('{}/health'.format(base_url), token)
    check('status is ok', h.get('status') == 'ok')
    check('version present', 'version' in h)

    section('2. Game events')
    events = [
        {'type': 'init_open'},
        {'type': 'init_missing',   'data': {'missing': 2}},
        {'type': 'init_all_ready'},
        {'type': 'init_prompt',    'data': {'hunter_id': 'H1', 'code': 'ABA'}},
        {'type': 'init_confirm',   'data': {'hunter_id': 'H1'}},
        {'type': 'init_complete'},
        {'type': 'game_start'},
        {'type': 'claim',          'data': {'hunter_id': 'H2'}},
        {'type': 'found',          'data': {'hunter_id': 'H1', 'treasure_id': 'T1'}},
        {'type': 'game_over',      'data': {'winner_id': 'H1', 'is_tie': False}},
        {'type': 'reset'},
    ]
    for e in events:
        r = _post('{}/event'.format(base_url), e, token)
        check('{} queued'.format(e['type']), r.get('queued') is True)

    section('3. Unknown route -> 404')
    import urllib.error
    try:
        _get('{}/nonexistent'.format(base_url), token)
        check('404 returned', False)
    except urllib.error.HTTPError as exc:
        check('404 returned', exc.code == 404)

    section('4. Game-over clears claim queue')
    _post('{}/event'.format(base_url), {'type': 'claim', 'data': {'hunter_id': 'H3'}}, token)
    _post('{}/event'.format(base_url), {'type': 'game_over', 'data': {}}, token)
    r = _post('{}/event'.format(base_url), {'type': 'reset'}, token)
    check('events accepted after game_over', r.get('queued') is True)

    print('\nResult: {} passed, {} failed'.format(len(PASS), len(FAIL)))
    return len(FAIL) == 0

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=7000)
    args = parser.parse_args()

    # Use a throwaway audio dir so smoke tests never leave silent stub WAVs
    # in the real audio/ folder (build_voice.py skips existing files by default).
    audio_dir = tempfile.mkdtemp(prefix='th_reachy_sim_')
    try:
        for wid in WAV_IDS:
            _make_silent_wav(os.path.join(audio_dir, '{}.wav'.format(wid)))

        # Lazy-import after stubs are in place
        sys.path.insert(0, HERE)
        import agent as agent_mod

        cfg = dict(agent_mod._DEFAULTS)
        cfg['bind_port'] = args.port
        cfg['audio_dir'] = audio_dir
        cfg['narrate'] = True
        cfg['emote'] = True
        cfg['track'] = False

        sys.modules['config'] = agent_mod._make_config_ns(cfg)
        agent_mod._agent = agent_mod.Agent(cfg)
        agent_mod._agent.start()

        time.sleep(0.3)

        server = agent_mod.ThreadingHTTPServer(('127.0.0.1', args.port), agent_mod._Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)

        base = 'http://127.0.0.1:{}'.format(args.port)
        ok = run_tests(base)
        time.sleep(0.5)
        server.shutdown()
        sys.exit(0 if ok else 1)
    finally:
        shutil.rmtree(audio_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
