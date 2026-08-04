# serial_reader.py — Threaded USB serial reader
#
# Reads the raw serial stream from the USB-connected Micro:bit (Player 2),
# parses each packet line, smooths RSSI values, updates GameState, and
# emits SocketIO events to the live dashboard.
#
# Packet formats received from Micro:bit 3 (Player 2):
#   "BALL,<rssi>"           — ball broadcast received at Player 2; rssi = P2's distance to ball
#   "P1:<ball_rssi>,<rssi>" — Player 1's self-reported ball RSSI, received at Player 2
#   "HOLDER:<id>,<rssi>"    — possession claim broadcast (used by ball LED, ignored here)

import threading
import time
from collections import deque

import serial
import serial.tools.list_ports

from config import SERIAL_PORT, BAUD_RATE, SMOOTH_WINDOW, USB_PLAYER_ID


class SerialReader(threading.Thread):
    """Background thread: reads serial port, parses packets, feeds GameState."""

    def __init__(self, socketio, state):
        super().__init__(daemon=True)
        self.socketio   = socketio
        self.state      = state
        self.running    = True
        self._histories: dict[str, deque] = {}
        self._connected = False
        self._last_error = ""

    def get_status(self) -> dict:
        return {
            "connected": self._connected,
            "port":      SERIAL_PORT,
            "error":     self._last_error,
        }

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
                time.sleep(2)           # wait before reconnect attempt

    # ── parsing ───────────────────────────────────────────────────────────────

    def _parse(self, line: str):
        """
        Dispatch each serial line to the correct handler.
        Any line that does not match expected formats is silently dropped.
        """
        try:
            parts = line.split(",", 1)          # split on first comma only
            if len(parts) != 2:
                return

            message, rssi_str = parts[0].strip(), parts[1].strip()
            bridge_rssi = int(rssi_str)

            if message == "BALL":
                # Ball broadcast received at Player 2 — this IS Player 2's distance to ball
                self._handle_ball_at_relay(bridge_rssi)

            elif message.startswith("P") and ":" in message:
                # Player broadcast: "P<id>:<ball_rssi>"
                player_part, ball_rssi_str = message.split(":", 1)
                player_id = player_part          # e.g. "P1"
                ball_rssi = int(ball_rssi_str)   # player's own distance to ball
                self._handle_player(player_id, ball_rssi, bridge_rssi)

            # HOLDER messages are ignored by the computer — ball LED handles those

        except (ValueError, IndexError):
            pass                                 # malformed packet — discard

    def _handle_ball_at_relay(self, raw_rssi: int):
        """BALL packet received by Player 2 — update P2's ball proximity."""
        smoothed = self._smooth(USB_PLAYER_ID, raw_rssi)
        changed  = self.state.update_player(USB_PLAYER_ID, smoothed)
        self.socketio.emit("rssi_update", {
            "player_id":  USB_PLAYER_ID,
            "ball_rssi":  smoothed,
            "raw_rssi":   raw_rssi,
            "holding":    changed["holding"],
            "total_s":    changed["total_seconds"],
            "possession": changed["possession_count"],
            "online":     True,
        })

    def _handle_player(self, player_id: str, ball_rssi: int, bridge_rssi: int):
        """Player broadcast overheard — update that player's ball proximity."""
        smoothed = self._smooth(player_id, ball_rssi)
        changed  = self.state.update_player(player_id, smoothed)
        self.socketio.emit("rssi_update", {
            "player_id":    player_id,
            "ball_rssi":    smoothed,
            "raw_rssi":     bridge_rssi,     # signal strength of this player at Player 2
            "holding":      changed["holding"],
            "total_s":      changed["total_seconds"],
            "possession":   changed["possession_count"],
            "online":       True,
        })

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
