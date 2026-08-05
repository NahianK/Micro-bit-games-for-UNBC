# serial_reader.py — Threaded USB serial reader for the Hide and Seek TEST setup
#
# ── REUSE NOTE ──────────────────────────────────────────────────────────────
# Structure identical to pass_the_ball_test_5_players/computer_app/serial_reader.py.
# Reused unchanged: threading pattern, run(), _smooth(), _emit_status(),
#                   get_status(), _connected/_last_error pattern.
# Changed:          _parse() handles HIDE/SEEK/TAGGED packet formats instead
#                   of BALL/P<id>/HOLDER formats.
# ────────────────────────────────────────────────────────────────────────────
#
# Serial line formats (sent by the USB-relay hider micro:bit):
#
#   "HIDE:H<id>,<rssi>"
#       Hider H<id> broadcast overheard by the relay.
#       rssi = hider's signal strength at the relay (positional reference).
#       → emits 'hider_signal' event.
#
#   "SEEK:H<id>:<seeker_rssi>,<relay_rssi>"
#       Seeker's self-reported distance to hider H<id>, relayed by bridge.
#       seeker_rssi = seeker's own RSSI reading from H<id> (what we care about).
#       relay_rssi  = seeker's signal strength at the relay.
#       → emits 'rssi_update' event with hider_id and seeker_rssi.
#
#   "TAGGED:H<id>,<rssi>"
#       Seeker pressed Button A near hider H<id> — hider is found.
#       → emits 'tagged' event with hider_id.

import threading
import time
from collections import deque

import serial

from config import SERIAL_PORT, BAUD_RATE, SMOOTH_WINDOW


class SerialReader(threading.Thread):
    """Background thread: reads relay serial port, parses packets, feeds state."""

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
        # REUSE: identical across all games
        return {"connected": self._connected, "port": SERIAL_PORT, "error": self._last_error}

    # ── public ────────────────────────────────────────────────────────────────

    def stop(self):
        self.running = False

    # ── thread entry ──────────────────────────────────────────────────────────
    # REUSE: run() method is identical across all games

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
    # GAME-SPECIFIC: packet format parsing for Hide and Seek

    def _parse(self, line: str):
        try:
            # All lines are "<message>,<relay_rssi>"
            parts = line.split(",", 1)
            if len(parts) != 2:
                return

            message    = parts[0].strip()
            relay_rssi = int(parts[1].strip())

            # ── HIDE:H<id> — hider broadcast seen by relay ────────────────────
            if message.startswith("HIDE:"):
                hider_id = message[5:]      # e.g. "H1"
                smoothed = self._smooth("HIDE_" + hider_id, relay_rssi)
                self.state.update_hider_signal(hider_id, smoothed)
                self.socketio.emit("hider_signal", {
                    "hider_id":   hider_id,
                    "rssi":       smoothed,
                    "raw_rssi":   relay_rssi,
                })

            # ── SEEK:H<id>:<seeker_rssi> — seeker proximity to a hider ───────
            elif message.startswith("SEEK:"):
                # message = "SEEK:H1:-65"  →  split on ":"  →  ["SEEK", "H1", "-65"]
                seg = message.split(":")
                if len(seg) != 3:
                    return
                hider_id    = seg[1]        # e.g. "H1"
                seeker_rssi = int(seg[2])   # seeker's RSSI reading from that hider
                smoothed    = self._smooth("SEEK_" + hider_id, seeker_rssi)
                self.state.update_seeker_proximity(hider_id, smoothed)
                self.socketio.emit("rssi_update", {
                    "hider_id":    hider_id,
                    "seeker_rssi": smoothed,
                    "raw_rssi":    relay_rssi,
                })

            # ── TAGGED:H<id> — seeker found a hider ──────────────────────────
            elif message.startswith("TAGGED:"):
                hider_id = message[7:]      # e.g. "H1"
                self.state.mark_found(hider_id)
                self.socketio.emit("tagged", {
                    "hider_id": hider_id,
                    "rssi":     relay_rssi,
                })

        except (ValueError, IndexError):
            pass

    # ── RSSI smoothing ────────────────────────────────────────────────────────
    # REUSE: _smooth() and _emit_status() are identical across all games

    def _smooth(self, key: str, value: int) -> int:
        if key not in self._histories:
            self._histories[key] = deque(maxlen=SMOOTH_WINDOW)
        self._histories[key].append(value)
        return int(sum(self._histories[key]) / len(self._histories[key]))

    def _emit_status(self, connected: bool, error: str = ""):
        self._connected  = connected
        self._last_error = error
        self.socketio.emit("serial_status", {
            "connected": connected,
            "port":      SERIAL_PORT,
            "error":     error,
        })
