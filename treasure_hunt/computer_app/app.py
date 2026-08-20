# app.py - Treasure Hunt FULL version
# Flask + SocketIO dashboard for up to 8 hunters and 5 treasures.
# Optional Reachy Mini agent and hunter identification via USB serial.

import atexit
import threading
import time
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO

from config import HOST, PORT, RSSI_HOT, RSSI_WARM, USE_REACHY
import serial_reader
import reachy_client
import registration as reg_module

# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------
class GameState:
    def __init__(self):
        self.reset()

    def setup(self, hunters, treasures, use_reachy=False):
        """Configure active hunters and treasures before game starts."""
        self.active_hunters   = ['H{}'.format(i) for i in range(1, hunters + 1)]
        self.active_treasures = ['T{}'.format(i) for i in range(1, treasures + 1)]
        self.hunters   = {}
        self.treasures = {}
        self.game_over = False
        self.use_reachy = use_reachy

    def is_game_over(self):
        if not self.active_treasures:
            return False
        return all(
            self.treasures.get(tid, {}).get('found_by') is not None
            for tid in self.active_treasures
        )

    def get_leaderboard(self):
        counts = {}
        for tid in self.active_treasures:
            finder = self.treasures.get(tid, {}).get('found_by')
            if finder:
                counts[finder] = counts.get(finder, 0) + 1
        for hid in self.active_hunters:
            counts.setdefault(hid, 0)
        return sorted(
            [{'hunter_id': hid, 'finds': n} for hid, n in counts.items()],
            key=lambda x: x['finds'],
            reverse=True,
        )

    def update_hunter(self, hunter_id, treasure_id, rssi):
        now  = time.time()
        prev = self.hunters.get(hunter_id, {})
        prev_best = prev.get('rssi_to_nearest')
        if prev_best is None or rssi > prev_best or \
                prev.get('nearest_treasure') == treasure_id:
            self.hunters[hunter_id] = {
                'nearest_treasure': treasure_id,
                'rssi_to_nearest':  rssi,
                'last_seen':        now,
                'claimed':          prev.get('claimed', False),
            }
        else:
            prev['last_seen'] = now
            self.hunters[hunter_id] = prev

    def mark_found(self, treasure_id, hunter_id):
        now = time.time()
        self.treasures[treasure_id] = {
            'found_by':         hunter_id,
            'found_time':       now,
            'signal_at_relay':  self.treasures.get(treasure_id, {}).get('signal_at_relay'),
            'last_seen':        now,
        }
        h = self.hunters.get(hunter_id, {})
        h['claimed'] = True
        self.hunters[hunter_id] = h

    def update_treasure_signal(self, treasure_id, relay_rssi):
        t = self.treasures.setdefault(treasure_id, {})
        t['signal_at_relay'] = relay_rssi
        t['last_seen']       = time.time()

    def get_snapshot(self):
        return {
            'active_hunters':   self.active_hunters,
            'active_treasures': self.active_treasures,
            'hunters':          self.hunters,
            'treasures':        self.treasures,
            'game_over':        self.game_over,
            'leaderboard':      self.get_leaderboard() if self.game_over else [],
            'use_reachy':       getattr(self, 'use_reachy', False),
        }

    def reset(self):
        self.active_hunters   = []
        self.active_treasures = []
        self.hunters   = {}
        self.treasures = {}
        self.game_over = False
        self.use_reachy = False


state = GameState()
_reg_session = None         # active RegistrationSession or None
_reg_ticker  = None         # background thread polling reg_session.tick()

# ---------------------------------------------------------------------------
# Flask + SocketIO
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'treasure-hunt-secret'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# ---------------------------------------------------------------------------
# Reachy status helper
# ---------------------------------------------------------------------------

def _reachy_status(health_body=None):
    """Return a small dict with robot availability info."""
    if not USE_REACHY:
        return {'enabled': False}
    h = health_body if health_body is not None else reachy_client.health()
    if h is None:
        return {'enabled': True, 'available': False, 'error': 'agent unreachable'}
    return {
        'enabled':          True,
        'available':        h.get('status') == 'ok',
        'robot_ready':      h.get('robot_ready', False),
        'tracker_running':  h.get('tracker_running', False),
        'version':          h.get('version', '?'),
    }


def _reachy_full_init():
    """
    Ask the agent for full robot bring-up (voice + camera tracking).
    Returns the /init JSON body, or None if the agent is unreachable.
    """
    result = reachy_client.init()
    if result:
        print('[reachy] full init ok — robot_ready={} tracker_running={}'.format(
            result.get('robot_ready'), result.get('tracker_running')))
    return result

# ---------------------------------------------------------------------------
# Registration ticker
# ---------------------------------------------------------------------------

def _start_reg_ticker():
    global _reg_ticker

    def _tick():
        global _reg_session
        while _reg_session is not None:
            alive = _reg_session.tick()
            if not alive:
                break
            time.sleep(0.4)

    _reg_ticker = threading.Thread(target=_tick, daemon=True)
    _reg_ticker.start()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/setup', methods=['GET'])
def setup_page():
    return render_template('setup.html', state=state,
                           reachy_status=_reachy_status())


@app.route('/setup', methods=['POST'])
def setup_post():
    global _reg_session

    try:
        hunters   = int(request.form.get('hunters', 1))
        treasures = int(request.form.get('treasures', 1))
        hunters   = max(1, min(8, hunters))
        treasures = max(1, min(5, treasures))
    except (ValueError, TypeError):
        hunters, treasures = 1, 1

    use_reachy = bool(request.form.get('use_reachy')) and USE_REACHY
    state.setup(hunters, treasures, use_reachy=use_reachy)

    if use_reachy:
        # Full robot bring-up (wake + voice + camera tracking), then verify.
        h = _reachy_full_init()
        if h is None:
            h = reachy_client.health()
        if h and h.get('status') == 'ok':
            socketio.emit('reachy_status', _reachy_status(h))
            _reg_session = reg_module.RegistrationSession(
                n_hunters=hunters,
                send_serial=serial_reader.send_line,
                reachy_client=reachy_client,
                socketio=socketio,
            )
            _reg_session.start()
            _start_reg_ticker()
            return redirect(url_for('initialize_page'))
        else:
            # Agent unreachable — fall through to normal start with a warning
            socketio.emit('reachy_status', {'available': False,
                                            'error': 'agent unreachable at start'})

    # Non-Reachy path (or Reachy health failed): start immediately.
    # Do NOT call reachy_client.event here — the agent is either disabled or
    # unreachable. For successful Reachy sessions, game_start is sent by on_reg_complete.
    serial_reader.signal_hunters_go()
    return redirect(url_for('index'))


@app.route('/initialize')
def initialize_page():
    if _reg_session is None:
        return redirect(url_for('index'))
    return render_template('initialize.html',
                           session=_reg_session.snapshot(),
                           n_hunters=len(state.active_hunters))


@app.route('/initialize/cancel', methods=['POST'])
def initialize_cancel():
    global _reg_session
    if _reg_session:
        _reg_session.cancel()
        _reg_session = None
    return redirect(url_for('index'))


@app.route('/')
def index():
    return render_template(
        'index.html',
        rssi_hot=RSSI_HOT,
        rssi_warm=RSSI_WARM,
        active_hunters=state.active_hunters,
        active_treasures=state.active_treasures,
        use_reachy=getattr(state, 'use_reachy', False),
    )


# ---------------------------------------------------------------------------
# SocketIO events
# ---------------------------------------------------------------------------

@socketio.on('connect')
def on_connect():
    socketio.emit('state_snapshot', state.get_snapshot())
    socketio.emit('serial_status',  serial_reader.get_status())
    socketio.emit('reachy_status',  _reachy_status())
    if _reg_session:
        socketio.emit('reg_snapshot', _reg_session.snapshot())


@socketio.on('reset_session')
def on_reset():
    global _reg_session
    if _reg_session:
        _reg_session.cancel()
        _reg_session = None
    state.reset()
    reachy_client.event('reset')
    socketio.emit('state_snapshot', state.get_snapshot())
    socketio.emit('redirect', {'url': url_for('setup_page')})


@socketio.on('reg_complete')
def on_reg_complete():
    """Dashboard signals that all hunters are ACK'd — start gameplay."""
    global _reg_session
    _reg_session = None
    serial_reader.signal_hunters_go()
    reachy_client.event('game_start')
    socketio.emit('redirect', {'url': url_for('index')})


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

@atexit.register
def _on_exit():
    try:
        reachy_client.event('reset')
    except Exception:
        pass


@app.route('/api/reachy_health')
def api_reachy_health():
    return jsonify(_reachy_status())


# ---------------------------------------------------------------------------
# Start serial reader and run app
# ---------------------------------------------------------------------------

def _get_reg_session():
    return _reg_session


if __name__ == '__main__':
    serial_reader.start_reader(socketio, state, reg_callback=_get_reg_session)
    if USE_REACHY:
        # Warm the robot as soon as the host app is up (voice + camera).
        # Session start calls init again — idempotent on the agent.
        threading.Thread(
            target=_reachy_full_init, daemon=True, name='reachy-init').start()
    socketio.run(app, host=HOST, port=PORT, debug=False)
