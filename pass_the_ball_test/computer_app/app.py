# app.py — Flask + SocketIO server
#
# Entry point for the computer application.
# Run with:  python app.py
# Then open: http://localhost:5000  (or http://<pi-ip>:5000 on Raspberry Pi B+)
#
# GameState tracks possession for every player ID seen on the serial stream.
# New players are added automatically — no configuration change needed.

import time
import threading

from flask import Flask, render_template
from flask_socketio import SocketIO

from config import HOST, PORT, RSSI_HOT, RSSI_WARM, PLAYER_TIMEOUT_S
from serial_reader import SerialReader

# ── Flask / SocketIO setup ────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "microbit-proximity-game"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# ── Game state ────────────────────────────────────────────────────────────────
class GameState:
    """
    Tracks ball proximity and possession for all players.
    Thread-safe via a simple lock — SerialReader and Flask run on separate threads.
    """

    def __init__(self):
        self._lock   = threading.Lock()
        self._players: dict[str, dict] = {}

    def update_player(self, player_id: str, ball_rssi: int) -> dict:
        now = time.time()
        with self._lock:
            if player_id not in self._players:
                self._players[player_id] = {
                    "ball_rssi":       ball_rssi,
                    "holding":         False,
                    "hold_start":      None,
                    "total_seconds":   0.0,
                    "possession_count": 0,
                    "last_seen":       now,
                }

            p = self._players[player_id]
            p["ball_rssi"] = ball_rssi
            p["last_seen"] = now

            # Possession logic — enter holding when ball is HOT
            if ball_rssi > RSSI_HOT:
                if not p["holding"]:
                    p["holding"]         = True
                    p["hold_start"]      = now
                    p["possession_count"] += 1
            else:
                if p["holding"]:
                    p["holding"] = False
                    if p["hold_start"] is not None:
                        p["total_seconds"] += now - p["hold_start"]
                        p["hold_start"]     = None

            return self._player_snapshot(p)

    def get_snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            result = {}
            for pid, p in self._players.items():
                online = (now - p["last_seen"]) < PLAYER_TIMEOUT_S
                snap   = self._player_snapshot(p)
                snap["online"] = online
                result[pid]    = snap
            return result

    def reset(self):
        with self._lock:
            self._players = {}

    @staticmethod
    def _player_snapshot(p: dict) -> dict:
        """Compute derived fields (current hold time) without mutating state."""
        current_hold = 0.0
        if p["holding"] and p["hold_start"] is not None:
            current_hold = time.time() - p["hold_start"]
        return {
            "ball_rssi":       p["ball_rssi"],
            "holding":         p["holding"],
            "total_seconds":   round(p["total_seconds"] + current_hold, 1),
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
    """Send full state snapshot and current serial status to newly connected browser."""
    socketio.emit("state_snapshot", state.get_snapshot())
    socketio.emit("serial_status", reader.get_status())


@socketio.on("reset_session")
def on_reset():
    """Clear all player tallies and re-broadcast empty state."""
    state.reset()
    socketio.emit("state_snapshot", state.get_snapshot())


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import socket as _socket
    try:
        _ip = _socket.gethostbyname(_socket.gethostname())
    except Exception:
        _ip = "unknown"
    reader.start()
    print(f"Dashboard (this device):  http://localhost:{PORT}")
    print(f"Dashboard (other devices on same WiFi): http://{_ip}:{PORT}")
    print("If other devices cannot connect, run this once in PowerShell (as Admin):")
    print(f"  netsh advfirewall firewall add rule name=\"Microbit Dashboard\" dir=in action=allow protocol=TCP localport={PORT}")
    socketio.run(app, host=HOST, port=PORT, debug=False, use_reloader=False)
