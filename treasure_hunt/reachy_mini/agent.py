#!/usr/bin/env python3
# agent.py — Treasure Hunt Reachy Mini agent.
#
# Run this ON the robot via SSH:
#   /venvs/apps_venv/bin/python agent.py [--config /path/to/config.json]
#
# It listens for game events from the Treasure Hunt computer app over HTTP and
# translates them into robot speech, expressions, and gaze.
#
# The Reachy Mini Control app does NOT need to be running. The low-level
# reachy-mini-daemon must be running (it starts automatically on power-on).
#
# ENDPOINTS
#   GET  /health  — liveness check; returns JSON
#   POST /init    — full session bring-up (wake, voice, camera tracking)
#   POST /event   — receive a game event; returns JSON
#
# AUTHENTICATION
#   If "token" is set in config.json, every request must carry:
#     Authorization: Bearer <token>
#   Leave token empty to allow unauthenticated access (safe on a trusted LAN).

import argparse
import collections
import json
import os
import sys
import threading
import time
import types
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_DEFAULTS = {
    'bind_host': '0.0.0.0',
    'bind_port': 7000,
    'token': '',
    'narrate': True,
    'emote': True,
    'wobble': True,
    'speak_pad_s': 0.35,
    'track': True,
    'tracker_fps': 8.0,
    'tracker_look_s': 0.7,
    'tracker_deadzone_px': 60,
    'tracker_min_face_px': 48,
    'tracker_lost_s': 4.0,
    'tracker_recentre_s': 12.0,
    'tracker_settle_s': 0.35,
    'audio_dir': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'audio'),
    'robot_timeout_s': 15.0,
    'speaker_volume': 100,
}


def _load_config(path):
    d = dict(_DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for k in d:
            if k in data:
                d[k] = data[k]
    return d


# ---------------------------------------------------------------------------
# Inject config module so robot.py and tracker.py can `import config`
# ---------------------------------------------------------------------------

def _make_config_ns(cfg):
    return types.SimpleNamespace(
        USE_ROBOT=True,
        ROBOT_HOST='localhost',
        ROBOT_PORT=8000,
        ROBOT_CONNECT_MODE='auto',
        ROBOT_TIMEOUT_S=cfg['robot_timeout_s'],
        ROBOT_NARRATES=cfg['narrate'],
        ROBOT_WOBBLE=cfg['wobble'],
        ROBOT_SPEAK_PAD_S=cfg['speak_pad_s'],
        ROBOT_EMOTES=cfg['emote'],
        ROBOT_SPEAKER_VOLUME=int(cfg.get('speaker_volume', 100)),
        ROBOT_PRELOAD_VOICES=True,
        USE_TRACKER=cfg['track'],
        TRACKER_FPS=cfg['tracker_fps'],
        TRACKER_LOOK_S=cfg['tracker_look_s'],
        TRACKER_DEADZONE_PX=cfg['tracker_deadzone_px'],
        TRACKER_MIN_FACE_PX=cfg['tracker_min_face_px'],
        TRACKER_LOST_S=cfg['tracker_lost_s'],
        TRACKER_RECENTRE_S=cfg['tracker_recentre_s'],
        TRACKER_SETTLE_S=cfg['tracker_settle_s'],
    )


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _wav_seconds(path):
    try:
        with wave.open(path, 'rb') as h:
            r = h.getframerate()
            return h.getnframes() / float(r) if r else None
    except Exception:
        return None


def _audio_path(audio_dir, name):
    return os.path.join(audio_dir, name + '.wav')


# ---------------------------------------------------------------------------
# Narrator queue
#
# game_over/reset clear lower-priority events. found removes pending claims.
# Priority levels:  0=game_over  1=found/init_complete  2=game_start/init
#                   3=claim  9=reset/neutral
# ---------------------------------------------------------------------------

class _NarratorQueue:
    def __init__(self):
        self._q = collections.deque()
        self._lock = threading.Lock()
        self._event = threading.Event()

    def push(self, event):
        etype = event.get('type', '')
        with self._lock:
            if etype in ('game_over', 'reset'):
                self._q.clear()
            elif etype == 'found':
                self._q = collections.deque(
                    e for e in self._q if e.get('type') != 'claim')
            self._q.append(event)
        self._event.set()

    def pop(self, timeout=1.0):
        if self._event.wait(timeout):
            with self._lock:
                if self._q:
                    e = self._q.popleft()
                    if not self._q:
                        self._event.clear()
                    return e
                self._event.clear()
        return None


# ---------------------------------------------------------------------------
# Agent — owns Robot, Tracker, and the narrator thread
# ---------------------------------------------------------------------------

class Agent:
    VERSION = '1.3'

    def __init__(self, cfg):
        self._cfg = cfg
        self._audio_dir = cfg['audio_dir']
        self._queue = _NarratorQueue()
        self._stop = threading.Event()
        self._robot = None
        self._tracker = None
        self._narrator = None
        self._lock = threading.Lock()

    # -- lifecycle -----------------------------------------------------------

    def start(self):
        self._init_robot()
        self._narrator = threading.Thread(
            target=self._narrator_loop, daemon=True, name='narrator')
        self._narrator.start()
        print('[agent] started - robot={} tracker={}'.format(
            getattr(self._robot, 'ready', False),
            getattr(self._tracker, 'running', False)))

    def stop(self):
        self._stop.set()
        if self._tracker:
            self._tracker.stop()
        if self._robot:
            self._robot.close()

    def _init_robot(self):
        import robot as robot_mod
        import tracker as tracker_mod
        self._robot = robot_mod.Robot(enabled=True)
        if not self._robot.ready:
            print('[agent] robot not ready: {}'.format(self._robot.error))
        self._tracker = tracker_mod.Tracker(self._robot)
        if self._cfg['track'] and self._robot.ready:
            self._tracker.start()
        if self._cfg['narrate'] and self._robot.ready:
            self._preload_audio()

    def _preload_audio(self):
        d = self._audio_dir
        if not os.path.isdir(d):
            return
        paths = [os.path.join(d, f) for f in os.listdir(d) if f.endswith('.wav')]
        n = self._robot.preload(paths)
        print('[agent] preloaded {}/{} WAVs'.format(n, len(paths)))

    def _ensure_voice(self):
        """Re-apply wake / wobble / speaker volume and preload narration WAVs."""
        r = self._robot
        if not getattr(r, 'ready', False):
            return
        try:
            if r.mini is not None:
                r.mini.wake_up()
                if self._cfg.get('wobble', True):
                    r.mini.enable_wobbling()
            r._set_speaker_volume()
        except Exception as exc:
            print('[agent] voice re-init warning: {}'.format(exc))
        if self._cfg.get('narrate', True):
            self._preload_audio()

    def _ensure_tracker(self):
        """Enable and start camera tracking (even if track was false at boot)."""
        if not getattr(self._robot, 'ready', False):
            return False
        import tracker as tracker_mod
        cfg_mod = sys.modules.get('config')
        if cfg_mod is not None:
            cfg_mod.USE_TRACKER = True
        if self._tracker is None or not getattr(self._tracker, 'enabled', False):
            self._tracker = tracker_mod.Tracker(self._robot, enabled=True)
        self._cfg['track'] = True
        ok = bool(self._tracker.start())
        if not ok:
            print('[agent] tracker did not start: {}'.format(
                getattr(self._tracker, 'error', 'unknown')))
        return ok

    def session_init(self):
        """
        Full Reachy bring-up for a game session: robot wake, voice path, and
        camera tracking. Idempotent — safe to call at app start and again when
        a Reachy-enabled session begins.
        """
        with self._lock:
            if self._robot is None or not getattr(self._robot, 'ready', False):
                self._init_robot()
            else:
                self._ensure_voice()
            tracker_ok = self._ensure_tracker()
            result = self.health()
            result['init'] = True
            result['tracker_started'] = tracker_ok
            print('[agent] session_init robot_ready={} tracker_running={}'.format(
                result.get('robot_ready'), result.get('tracker_running')))
            return result

    # -- status --------------------------------------------------------------

    def health(self):
        return {
            'status': 'ok',
            'version': self.VERSION,
            'robot_ready': bool(getattr(self._robot, 'ready', False)),
            'tracker_running': bool(getattr(self._tracker, 'running', False)),
            'narrate': bool(self._cfg.get('narrate', True)),
        }

    # -- event dispatch ------------------------------------------------------

    def handle_event(self, event):
        """Called from the HTTP handler thread. Returns quickly."""
        self._queue.push(event)
        return {'queued': True}

    # -- narrator thread -----------------------------------------------------

    def _narrator_loop(self):
        while not self._stop.is_set():
            event = self._queue.pop(timeout=0.5)
            if event is None:
                continue
            try:
                self._dispatch(event)
            except Exception as exc:
                print('[agent] error in narrator: {}'.format(exc))

    def _dispatch(self, event):
        etype = event.get('type', '')
        data = event.get('data', {})
        r = self._robot

        if etype == 'init_open':
            r.express('listen')
            self._say('init_open')

        elif etype == 'init_missing':
            n = int(data.get('missing', 1))
            n = min(max(n, 1), 7)
            self._say('init_missing_{}'.format(n))

        elif etype == 'init_all_ready':
            r.express('pass')
            self._say('init_all_ready')

        elif etype == 'init_prompt':
            hid = data.get('hunter_id', 'H1')
            code = data.get('code', 'AAA')
            hnum = _hid_num(hid)
            r.express('tell')
            self._say_seq(['hunter_{}'.format(hnum),
                           'code_{}'.format(code)])

        elif etype == 'init_confirm':
            hid = data.get('hunter_id', 'H1')
            r.express('pass')
            self._say('init_confirm_{}'.format(_hid_num(hid)))

        elif etype == 'init_retry':
            r.express('fail')
            self._say('init_retry')

        elif etype == 'init_complete':
            r.express('pass')
            self._say('init_complete')

        elif etype == 'init_cancel':
            r.express('neutral')
            self._say('init_cancel')

        elif etype == 'game_start':
            r.express('listen')
            self._say('game_start')

        elif etype == 'claim':
            hid = data.get('hunter_id', 'H1')
            hnum = _hid_num(hid)
            r.express('listen')
            self._say_seq(['claim_pre', 'hunter_{}'.format(hnum), 'claim_post'])

        elif etype == 'found':
            # Compose: "Yes! Hunter N, has found treasure M!"
            # Fragments avoid pre-rendering every hunter×treasure combo.
            hid = data.get('hunter_id', 'H1')
            tid = data.get('treasure_id', 'T1')
            hnum = _hid_num(hid)
            tnum = _tid_num(tid)
            r.express('pass')
            self._say_seq(['found_pre',
                           'hunter_{}'.format(hnum),
                           'found_post_T{}'.format(tnum)])

        elif etype == 'game_over':
            r.express('pass')
            self._say('game_over')
            winner = data.get('winner_id')
            is_tie = data.get('is_tie', False)
            time.sleep(0.4)
            if is_tie:
                self._say('winner_tie')
            elif winner:
                self._say('winner_{}'.format(_hid_num(winner)))

        elif etype == 'reset':
            r.express('neutral')

    # -- audio helpers -------------------------------------------------------

    def _say(self, name):
        if not getattr(self._robot, 'ready', False):
            return
        if not self._cfg['narrate']:
            return
        path = _audio_path(self._audio_dir, name)
        if not os.path.exists(path):
            print('[agent] WAV missing: {}'.format(path))
            return
        ok = self._robot.speak(path, wait=True)
        if not ok:
            print('[agent] speak failed: {}'.format(path))

    def _say_seq(self, names):
        for name in names:
            self._say(name)


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

_agent = None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress access log; agent.py prints its own

    def _auth_ok(self):
        token = _agent._cfg.get('token', '')
        if not token:
            return True
        auth = self.headers.get('Authorization', '')
        return auth == 'Bearer {}'.format(token)

    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health':
            if not self._auth_ok():
                self._reply(401, {'error': 'unauthorized'})
                return
            self._reply(200, _agent.health())
        else:
            self._reply(404, {'error': 'not found'})

    def do_POST(self):
        if not self._auth_ok():
            self._reply(401, {'error': 'unauthorized'})
            return

        if self.path == '/init':
            # Body is optional; empty or "{}" is fine.
            length = int(self.headers.get('Content-Length', 0))
            if length:
                try:
                    self.rfile.read(length)
                except Exception:
                    pass
            self._reply(200, _agent.session_init())
            return

        if self.path != '/event':
            self._reply(404, {'error': 'not found'})
            return
        length = int(self.headers.get('Content-Length', 0))
        try:
            body = json.loads(self.rfile.read(length).decode())
        except Exception:
            self._reply(400, {'error': 'bad json'})
            return
        result = _agent.handle_event(body)
        self._reply(200, result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _hid_num(hid):
    """'H3' → '3', 'H12' → '12', anything else → '1'. Clamped to 1..8."""
    try:
        n = int(str(hid).lstrip('Hh'))
    except (ValueError, AttributeError, TypeError):
        return '1'
    if n < 1:
        n = 1
    if n > 8:
        n = 8
    return str(n)


def _tid_num(tid):
    """'T2' → '2', anything else → '1'. Clamped to 1..5."""
    try:
        n = int(str(tid).lstrip('Tt'))
    except (ValueError, AttributeError, TypeError):
        return '1'
    if n < 1:
        n = 1
    if n > 5:
        n = 5
    return str(n)


def main():
    global _agent

    parser = argparse.ArgumentParser(description='Treasure Hunt Reachy Mini agent')
    parser.add_argument('--config', default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'config.json'),
        help='Path to config.json (default: ./config.json)')
    args = parser.parse_args()

    cfg = _load_config(args.config)

    # Inject the config namespace before importing robot/tracker
    sys.modules['config'] = _make_config_ns(cfg)
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    _agent = Agent(cfg)
    _agent.start()

    host = cfg['bind_host']
    port = int(cfg['bind_port'])
    # Threading so GET /health stays responsive while POST /init (or a busy
    # tracker/narrator on other threads) would otherwise stall a single-threaded
    # HTTPServer and make the dashboard flap reachable/unreachable.
    server = ThreadingHTTPServer((host, port), _Handler)
    print('[agent] listening on {}:{}'.format(host, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print('[agent] shutting down')
        _agent.stop()
        server.server_close()


if __name__ == '__main__':
    main()
