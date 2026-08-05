# app.py — Flask + SocketIO server for the 6-micro:bit Pass the Ball setup
#
# Run with:  python app.py
# Dashboard: http://localhost:5000
# On Pi B+:  http://<pi-ip>:5000

import time
import threading

from flask import Flask, render_template
from flask_socketio import SocketIO

from config import HOST, PORT, RSSI_HOT, RSSI_WARM, PLAYER_TIMEOUT_S
from serial_reader import SerialReader

app = Flask(__name__)
app.config["SECRET_KEY"] = "microbit-proximity-game"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# ── Game state ────────────────────────────────────────────────────────────────

class GameState:
    """
    Tracks:
      ball_position — smoothed bridge-to-ball RSSI (positional reference)
      players       — possession state and tallies per player ID
    """

    def __init__(self):
        self._lock         = threading.Lock()
        self._players: dict[str, dict] = {}
        self.ball_position = -100

    def update_ball_position(self, rssi: int):
        with self._lock:
            self.ball_position = rssi

    def update_player(self, player_id: str, ball_rssi: int) -> dict:
        now = time.time()
        with self._lock:
            if player_id not in self._players:
                self._players[player_id] = {
                    "ball_rssi":        ball_rssi,
                    "holding":          False,
                    "hold_start":       None,
                    "total_seconds":    0.0,
                    "possession_count": 0,
                    "last_seen":        now,
                }

            p = self._players[player_id]
            p["ball_rssi"] = ball_rssi
            p["last_seen"] = now

            if ball_rssi > RSSI_HOT:
                if not p["holding"]:
                    p["holding"]          = True
                    p["hold_start"]       = now
                    p["possession_count"] += 1
            else:
                if p["holding"]:
                    p["holding"] = False
                    if p["hold_start"] is not None:
                        p["total_seconds"] += now - p["hold_start"]
                        p["hold_start"]     = None

            return self._snapshot(p)

    def get_snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            players = {}
            for pid, p in self._players.items():
                snap           = self._snapshot(p)
                snap["online"] = (now - p["last_seen"]) < PLAYER_TIMEOUT_S
                players[pid]   = snap
            return {
                "ball_position": self.ball_position,
                "players":       players,
            }

    def reset(self):
        with self._lock:
            self._players    = {}
            self.ball_position = -100

    @staticmethod
    def _snapshot(p: dict) -> dict:
        current = 0.0
        if p["holding"] and p["hold_start"] is not None:
            current = time.time() - p["hold_start"]
        return {
            "ball_rssi":        p["ball_rssi"],
            "holding":          p["holding"],
            "total_seconds":    round(p["total_seconds"] + current, 1),
            "possession_count": p["possession_count"],
        }


state  = GameState()
reader = SerialReader(socketio, state)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", rssi_hot=RSSI_HOT, rssi_warm=RSSI_WARM)


# ── SocketIO events ───────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    """Send full state + current serial status to any newly connected browser."""
    socketio.emit("state_snapshot", state.get_snapshot())
    socketio.emit("serial_status", reader.get_status())

@socketio.on("reset_session")
def on_reset():
    state.reset()
    socketio.emit("state_snapshot", state.get_snapshot())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    reader.start()
    print(f"Dashboard: http://localhost:{PORT}")
    print(f"On network: http://<your-ip>:{PORT}")
    socketio.run(app, host=HOST, port=PORT, debug=False, use_reloader=False)
