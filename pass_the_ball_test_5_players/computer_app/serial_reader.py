# serial_reader.py — Threaded USB serial reader for the 6-micro:bit setup
#
# The Bridge micro:bit (Micro:bit 1) relays every radio packet it receives
# over USB serial. This module reads that stream, parses each line, and
# dispatches events to GameState and the SocketIO dashboard.
#
# Packet types received from the Bridge:
#
#   "BALL,<rssi>"
#       Ball broadcast overheard by the bridge.
#       rssi = bridge's distance to the ball (positional reference).
#       NOT attributed to any player — used for the Ball Position indicator.
#
#   "P<id>:<ball_rssi>,<bridge_rssi>"
#       Player broadcast overheard by the bridge.
#       ball_rssi = that player's self-reported distance to the ball.
#       bridge_rssi = that player's signal strength at the bridge.
#       ball_rssi is used for possession tracking.
#
#   "HOLDER:<id>,<rssi>"
#       Possession claim — used by the ball's LED. Ignored here.

import threading
import time
from collections import deque

import serial

from config import SERIAL_PORT, BAUD_RATE, SMOOTH_WINDOW


class SerialReader(threading.Thread):
    """Background thread: reads bridge serial port, parses packets, feeds state."""

    def __init__(self, socketio, state):
        super().__init__(daemon=True)
        self.socketio    = socketio
        self.state       = state
        self.running     = True
        self._histories: dict[str, deque] = {}
        self._connected  = False
        self._last_error = ""

    def get_status(self) -> dict:
        """Return current serial connection status for new browser connections."""
        return {"connected": self._connected, "port": SERIAL_PORT, "error": self._last_error}

    # ── public ────────────────────────────────────────────────────────────────

    def stop(self):
        self.running = False

    # ── thread entry ──────────────────────────────────────────────────────────

    def run(self):
        while self.running:
            try:
                with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
                    self._emit_status(True)
                    while self.running:
                        raw = ser.readline()
                        if raw:
                            line = raw.decode("utf-8", errors="ignore").strip()
                            if line:
                                self._parse(line)
            except serial.SerialException as exc:
                self._emit_status(False, str(exc))
                time.sleep(2)

    # ── parsing ───────────────────────────────────────────────────────────────

    def _parse(self, line: str):
        try:
            parts = line.split(",", 1)
            if len(parts) != 2:
                return

            message    = parts[0].strip()
            bridge_rssi = int(parts[1].strip())

            if message == "BALL":
                # Ball signal at the bridge — positional reference, not a player
                smoothed = self._smooth("BALL_AT_BRIDGE", bridge_rssi)
                self.state.update_ball_position(smoothed)
                self.socketio.emit("ball_position", {
                    "rssi":    smoothed,
                    "raw":     bridge_rssi,
                })

            elif message.startswith("P") and ":" in message:
                # Player broadcast: "P<id>:<ball_rssi>"
                player_id, ball_rssi_str = message.split(":", 1)
                ball_rssi = int(ball_rssi_str)
                smoothed  = self._smooth(player_id, ball_rssi)
                updated   = self.state.update_player(player_id, smoothed)
                self.socketio.emit("rssi_update", {
                    "player_id":    player_id,
                    "ball_rssi":    smoothed,
                    "raw_rssi":     bridge_rssi,
                    "holding":      updated["holding"],
                    "total_s":      updated["total_seconds"],
                    "possession":   updated["possession_count"],
                    "online":       True,
                })

            # HOLDER packets: ignored by the computer app

        except (ValueError, IndexError):
            pass

    # ── RSSI smoothing ────────────────────────────────────────────────────────

    def _smooth(self, key: str, value: int) -> int:
        if key not in self._histories:
            self._histories[key] = deque(maxlen=SMOOTH_WINDOW)
        self._histories[key].append(value)
        return int(sum(self._histories[key]) / len(self._histories[key]))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _emit_status(self, connected: bool, error: str = ""):
        self._connected  = connected
        self._last_error = error
        self.socketio.emit("serial_status", {
            "connected": connected,
            "port":      SERIAL_PORT,
            "error":     error,
        })
