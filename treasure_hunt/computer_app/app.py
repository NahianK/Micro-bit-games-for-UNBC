# app.py - Treasure Hunt FULL version
# Flask + SocketIO dashboard for up to 5 hunters and 5 treasures.
# REUSE: identical to treasure_hunt_test\computer_app\app.py.

import time
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO

from config import HOST, PORT, RSSI_HOT, RSSI_WARM
import serial_reader

# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------
class GameState:
    def __init__(self):
        self.reset()

    def setup(self, hunters, treasures):
        """Configure active hunters and treasures before game starts."""
        self.active_hunters   = ['H{}'.format(i) for i in range(1, hunters + 1)]
        self.active_treasures = ['T{}'.format(i) for i in range(1, treasures + 1)]
        self.hunters   = {}
        self.treasures = {}

    def update_hunter(self, hunter_id, treasure_id, rssi):
        """Called when a HUNT packet arrives; track nearest treasure."""
        now  = time.time()
        prev = self.hunters.get(hunter_id, {})
        prev_best = prev.get('rssi_to_nearest')

        if prev_best is None or rssi > prev_best or prev.get('nearest_treasure') == treasure_id:
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
        """Called when a FOUND packet confirms a find."""
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
        """Update bridge-side signal for a treasure beacon."""
        t = self.treasures.setdefault(treasure_id, {})
        t['signal_at_relay'] = relay_rssi
        t['last_seen']       = time.time()

    def get_snapshot(self):
        return {
            'active_hunters':   self.active_hunters,
            'active_treasures': self.active_treasures,
            'hunters':          self.hunters,
            'treasures':        self.treasures,
        }

    def reset(self):
        self.active_hunters   = []
        self.active_treasures = []
        self.hunters   = {}
        self.treasures = {}


state = GameState()

# ---------------------------------------------------------------------------
# Flask + SocketIO
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'treasure-hunt-secret'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/setup', methods=['GET'])
def setup_page():
    return render_template('setup.html', state=state)


@app.route('/setup', methods=['POST'])
def setup_post():
    try:
        hunters   = int(request.form.get('hunters', 1))
        treasures = int(request.form.get('treasures', 1))
        hunters   = max(1, min(5, hunters))
        treasures = max(1, min(5, treasures))
    except (ValueError, TypeError):
        hunters, treasures = 1, 1
    state.setup(hunters, treasures)
    return redirect(url_for('index'))


@app.route('/')
def index():
    return render_template(
        'index.html',
        rssi_hot=RSSI_HOT,
        rssi_warm=RSSI_WARM,
        active_hunters=state.active_hunters,
        active_treasures=state.active_treasures,
    )


# ---------------------------------------------------------------------------
# SocketIO events
# ---------------------------------------------------------------------------
@socketio.on('connect')
def on_connect():
    socketio.emit('state_snapshot', state.get_snapshot())
    socketio.emit('serial_status',  serial_reader.get_status())


@socketio.on('reset_session')
def on_reset():
    state.reset()
    socketio.emit('state_snapshot', state.get_snapshot())
    socketio.emit('redirect', {'url': url_for('setup_page')})


# Monkey-patch socketio.emit so serial_reader treasure_signal events update state
_orig_emit = socketio.emit


def _patched_emit(event, data=None, **kwargs):
    if event == 'treasure_signal' and data:
        state.update_treasure_signal(data.get('treasure_id', ''), data.get('relay_rssi', 0))
    _orig_emit(event, data, **kwargs)


socketio.emit = _patched_emit

# ---------------------------------------------------------------------------
# Start serial reader and run app
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    serial_reader.start_reader(socketio, state)
    socketio.run(app, host=HOST, port=PORT, debug=False)
