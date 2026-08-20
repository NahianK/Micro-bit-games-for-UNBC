# reachy_client.py — lightweight HTTP client for the Reachy Mini agent.
#
# Uses only standard-library urllib so the game host does not need any extra
# packages and can run on a Raspberry Pi B+ or any machine that runs the app.
#
# Every call is fire-and-forget with a short timeout. If the agent is
# unreachable the call logs a one-time warning and returns False. Game state
# is never altered by the return value; Reachy is ornamental.

import json
import threading
import urllib.error
import urllib.request

import config

_warned = False


def _url(path):
    host = config.REACHY_AGENT_HOST
    port = config.REACHY_AGENT_PORT
    return 'http://{}:{}{}'.format(host, port, path)


def _headers():
    h = {'Content-Type': 'application/json'}
    tok = getattr(config, 'REACHY_AGENT_TOKEN', '')
    if tok:
        h['Authorization'] = 'Bearer {}'.format(tok)
    return h


def health():
    """
    GET /health.  Returns the parsed JSON body, or None on any failure.
    """
    if not getattr(config, 'USE_REACHY', False):
        return None
    try:
        req = urllib.request.Request(_url('/health'), headers=_headers())
        with urllib.request.urlopen(req, timeout=config.REACHY_HEALTH_TIMEOUT_S) as r:
            return json.loads(r.read())
    except Exception:
        return None


def init():
    """
    POST /init — full Reachy session bring-up on the robot:
    wake, speaker volume / voice path, and camera tracking.

    Returns the parsed JSON body (same shape as /health plus init flags),
    or None on any failure. Blocking — call from a background thread at app
    start, or once when a Reachy-enabled session begins.
    """
    if not getattr(config, 'USE_REACHY', False):
        return None
    # Init can preload WAVs and start the tracker; allow longer than health.
    timeout = max(float(config.REACHY_HEALTH_TIMEOUT_S), 20.0)
    try:
        req = urllib.request.Request(
            _url('/init'), data=b'{}', headers=_headers(), method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        global _warned
        if not _warned:
            print('[reachy] init failed: {}'.format(exc))
            _warned = True
        return None


def event(event_type, **data):
    """
    POST /event with {type, data} on a background thread so serial parsing is
    never stalled. Returns True immediately; fires-and-forgets.
    """
    if not getattr(config, 'USE_REACHY', False):
        return True  # Reachy disabled — no-op, no timeout

    t = threading.Thread(target=_send_event, args=(event_type, data), daemon=True)
    t.start()
    return True


def _send_event(event_type, data):
    global _warned
    body = json.dumps({'type': event_type, 'data': data}).encode()
    req = urllib.request.Request(
        _url('/event'), data=body, headers=_headers(), method='POST')
    try:
        with urllib.request.urlopen(req, timeout=config.REACHY_EVENT_TIMEOUT_S) as r:
            r.read()
            _warned = False
    except urllib.error.URLError as exc:
        if not _warned:
            print('[reachy] unreachable: {}'.format(exc.reason))
            _warned = True
    except Exception as exc:
        if not _warned:
            print('[reachy] error: {}'.format(exc))
            _warned = True
