# app.py — Flask + SocketIO server for the Hide and Seek TEST setup
#
# ── REUSE NOTE ──────────────────────────────────────────────────────────────
# Structure identical to pass_the_ball_test_5_players/computer_app/app.py.
# Reused unchanged: Flask/SocketIO setup, on_connect(), on_reset(), entry point.
# Changed:          GameState tracks per-hider seeker proximity and found status
#                   instead of per-player possession and ball holding.
# ────────────────────────────────────────────────────────────────────────────
#
# Run with:  python app.py
# Dashboard: http://localhost:5000
# On Pi B+:  http://<pi-ip>:5000

import time
import threading

from flask import Flask, render_template
from flask_socketio import SocketIO

from config import HOST, PORT, RSSI_HOT, RSSI_WARM, HIDER_TIMEOUT_S
from serial_reader import SerialReader

app = Flask(__name__)
app.config["SECRET_KEY"] = "microbit-hide-and-seek"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# ── Game state ────────────────────────────────────────────────────────────────

class GameState:
    """
    Tracks per-hider state:
      seeker_rssi    — smoothed seeker-to-hider RSSI (from SEEK packets)
      signal_at_relay — smoothed hider signal at relay (from HIDE packets)
      found          — True once seeker presses Button A near this hider
      found_time     — time.time() when hider was tagged
      last_seen      — time.time() of last SEEK update for this hider
      hide_start     — time.time() when this hider was first detected
    """

    def __init__(self):
        self._lock             = threading.Lock()
        self._hiders: dict[str, dict] = {}
        self._game_start       = time.time()

    def _ensure_hider(self, hider_id: str) -> dict:
        """Create hider entry on first contact."""
        if hider_id not in self._hiders:
            self._hiders[hider_id] = {
                "seeker_rssi":     -100,
                "signal_at_relay": -100,
                "found":           False,
                "found_time":      None,
                "last_seen":       time.time(),
                "hide_start":      time.time(),
            }
        return self._hiders[hider_id]

    def update_seeker_proximity(self, hider_id: str, rssi: int):
        """Called when a SEEK packet arrives — seeker's distance to this hider."""
        with self._lock:
            h = self._ensure_hider(hider_id)
            if not h["found"]:
                h["seeker_rssi"] = rssi
                h["last_seen"]   = time.time()

    def update_hider_signal(self, hider_id: str, rssi: int):
        """Called when a HIDE packet arrives — hider's signal at the relay."""
        with self._lock:
            h = self._ensure_hider(hider_id)
            h["signal_at_relay"] = rssi

    def mark_found(self, hider_id: str):
        """Called when a TAGGED packet arrives — mark hider as found."""
        with self._lock:
            h = self._ensure_hider(hider_id)
            if not h["found"]:
                h["found"]      = True
                h["found_time"] = time.time()

    def get_snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            hiders = {}
            for hid, h in self._hiders.items():
                elapsed = now - h["hide_start"]
                online  = (now - h["last_seen"]) < HIDER_TIMEOUT_S
                hiders[hid] = {
                    "seeker_rssi":     h["seeker_rssi"],
                    "signal_at_relay": h["signal_at_relay"],
                    "found":           h["found"],
                    "found_time":      h["found_time"],
                    "hide_seconds":    round(elapsed, 1),
                    "online":          online,
                }
            return {"hiders": hiders, "game_start": self._game_start}

    def reset(self):
        with self._lock:
            self._hiders     = {}
            self._game_start = time.time()


state  = GameState()
reader = SerialReader(socketio, state)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", rssi_hot=RSSI_HOT, rssi_warm=RSSI_WARM)


# ── SocketIO events ───────────────────────────────────────────────────────────
# REUSE: on_connect() and on_reset() pattern identical across all games

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
