# app.py - Quest Engine gamemaster console.
#
#     cd computer_app
#     pip install -r requirements.txt
#     python app.py
#
# Then open http://localhost:5000 (or http://<pi-ip>:5000 from a laptop).
#
# THIS SCREEN IS FOR THE GAMEMASTER ONLY. The children are not supposed to see
# a screen at all - they get the narrator's voice, the lights on their wands and
# whatever is written on the whiteboard. Turn the laptop away from the room.
#
# REUSE: Flask + SocketIO skeleton follows the same shape as app.py in the
# other games in this repo. The difference is that the state lives in engine.py
# rather than in this file, because a scenario is a good deal more than a
# scoreboard.

import socket
import threading
import time

from flask import Flask, render_template
from flask_socketio import SocketIO

import config
import protocol as P
from audio import Audio
from engine import Engine
from robot import Robot
from tracker import Tracker
from transports import SerialBridgeTransport

app = Flask(__name__)
app.config['SECRET_KEY'] = 'quest-engine-secret'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

transport = SerialBridgeTransport(config.SERIAL_PORT, config.BAUD_RATE)

# Both are safe to build unconditionally: with USE_ROBOT / USE_TRACKER off, or
# with no robot on the network, they become objects whose methods do nothing.
# Connecting happens here rather than in __main__ so the banner can report it.
robot = Robot()
tracker = Tracker(robot)


def push_state(snapshot):
    """Engine callback. Fires on every meaningful change."""
    socketio.emit('state', snapshot)


engine = Engine(transport, lambda pack_id: Audio(pack_id, robot=robot),
                on_update=push_state, robot=robot)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template(
        'gm.html',
        verbs=P.verb_help(),
        bearings=P.BEARINGS,
        max_players=config.ACTIVE_PLAYERS,
        difficulties=sorted(config.DIFFICULTY_WINDOW_SCALE),
    )


# ---------------------------------------------------------------------------
# SocketIO
# ---------------------------------------------------------------------------
@socketio.on('connect')
def on_connect():
    socketio.emit('state', engine.snapshot())
    missing = engine.missing_voice_lines()
    socketio.emit('voices', {
        'missing': len(missing),
        'examples': missing[:6],
    })


@socketio.on('control')
def on_control(data):
    data = data or {}
    action = data.get('action')

    if action == 'start':
        engine.start(int(data.get('from_index', 0) or 0))
    elif action == 'pause':
        engine.pause()
    elif action == 'resume':
        engine.resume()
    elif action == 'stop':
        engine.stop()
    elif action == 'skip':
        engine.skip()
    elif action == 'pass':
        engine.override('pass')
    elif action == 'fail':
        engine.override('fail')
    elif action == 'idle':
        engine.send_idle()
    elif action == 'difficulty':
        engine.set_difficulty(data.get('value'))
    elif action == 'tracking':
        # A get-out for the gamemaster when the robot's head-turning is
        # competing with the narrator for the children's attention.
        if data.get('value') in (False, 'off', 'false', 0):
            tracker.pause()
            engine.note('robot: stopped looking around')
        else:
            tracker.resume()
            engine.note('robot: looking around again')
    elif action == 'pack':
        try:
            engine.stop()
            engine.load_pack(data.get('value'))
            socketio.emit('voices', {
                'missing': len(engine.missing_voice_lines()),
                'examples': engine.missing_voice_lines()[:6],
            })
        except Exception as exc:
            engine.note('could not load that pack: {}'.format(exc))
    elif action == 'manual':
        arg = data.get('arg')
        if arg in ('', None):
            arg = None
        win = data.get('win')
        try:
            win = int(win) if win not in ('', None) else None
        except (TypeError, ValueError):
            win = None
        engine.send_manual(
            data.get('verb', 'BTNA'),
            arg=arg,
            win=win,
            who=data.get('who', 'all'),
        )

    socketio.emit('state', engine.snapshot())


# ---------------------------------------------------------------------------
# Ticker: keeps the countdown and the roster "seconds ago" figures live even
# when nothing else is happening.
# ---------------------------------------------------------------------------
def ticker():
    while True:
        time.sleep(0.4)
        try:
            socketio.emit('state', engine.snapshot())
        except Exception:
            pass


if __name__ == '__main__':
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = 'unknown'

    transport.start(engine.on_message)
    tracker.start()
    threading.Thread(target=ticker, daemon=True).start()

    print('=' * 68)
    print(' Quest Engine - gamemaster console')
    print(' Bridge port : {}'.format(config.SERIAL_PORT))
    print(' Pack        : {}'.format(engine.pack_id))
    print(' Audio       : {}'.format(engine.audio.describe()))
    print(' Robot       : {}'.format(robot.describe()))
    print(' Tracking    : {}'.format(tracker.describe()))
    missing = engine.missing_voice_lines()
    if missing:
        print(' Voices      : {} line(s) not built yet - they will be printed'
              ' instead. Run tools/build_voice.py.'.format(len(missing)))
    print(' Console     : http://localhost:{}'.format(config.PORT))
    print(' Other PCs   : http://{}:{}'.format(local_ip, config.PORT))
    print(' Remember: keep this screen turned away from the children.')
    print('=' * 68)

    try:
        socketio.run(app, host=config.HOST, port=config.PORT, debug=False,
                     allow_unsafe_werkzeug=True)
    finally:
        # Leave the robot folded down rather than holding a pose against its
        # servos until somebody pulls the power.
        tracker.stop()
        robot.close()
