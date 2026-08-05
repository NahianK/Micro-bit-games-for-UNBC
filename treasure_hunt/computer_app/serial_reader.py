# serial_reader.py - Treasure Hunt FULL version
# Reads serial output from the dedicated bridge micro:bit (mb_bridge.py).
# Parses treasure hunt radio packets and emits SocketIO events.
# REUSE: identical to treasure_hunt_test\computer_app\serial_reader.py.
# The only difference is the source of the serial stream (bridge vs relay-treasure).

import threading
import time
from collections import deque

import serial
from config import SERIAL_PORT, BAUD_RATE, SMOOTH_WINDOW

# ---------------------------------------------------------------------------
# Module-level state (thread-safe via _lock)
# ---------------------------------------------------------------------------
_connected  = False
_last_error = None
_lock       = threading.Lock()

# Smoothing buffers: { (hunter_id, treasure_id): deque([rssi, ...]) }
_smooth_buffers = {}


def get_status():
    """Return serial connection status dict for dashboard badge."""
    with _lock:
        return {
            'connected': _connected,
            'port':      SERIAL_PORT,
            'error':     _last_error,
        }


def _smooth_rssi(key, new_val):
    """Exponential moving average over SMOOTH_WINDOW samples."""
    buf = _smooth_buffers.setdefault(key, deque(maxlen=SMOOTH_WINDOW))
    buf.append(new_val)
    return sum(buf) / len(buf)


# ---------------------------------------------------------------------------
# Packet parsers
# ---------------------------------------------------------------------------
def _parse_line(raw_line, socketio, state):
    """
    Parse one comma-terminated serial line and emit SocketIO events.

    Line formats (from bridge micro:bit):
        TRS:T1,-72          → treasure T1 signal seen at bridge
        HUNT:H1:T1:-65,-58  → hunter H1 is -65 dBm from T1, bridge sees hunter at -58
        CLAIM:H1,-45        → hunter H1 pressed Button B (claiming a find)
        FOUND:T1:H1,-40     → treasure T1 confirms found by hunter H1
    """
    line = raw_line.strip()
    if not line or ',' not in line:
        return

    try:
        last_comma = line.rfind(',')
        payload    = line[:last_comma]
        relay_rssi = int(line[last_comma + 1:])
    except (ValueError, IndexError):
        return

    # --- TRS:T<id> ---
    if payload.startswith('TRS:'):
        parts = payload.split(':')
        if len(parts) == 2:
            treasure_id = parts[1]
            socketio.emit('treasure_signal', {
                'treasure_id': treasure_id,
                'relay_rssi':  relay_rssi,
            })

    # --- HUNT:H<id>:T<id>:<rssi> ---
    elif payload.startswith('HUNT:'):
        parts = payload.split(':')
        if len(parts) == 4:
            hunter_id   = parts[1]
            treasure_id = parts[2]
            try:
                hunter_rssi = int(parts[3])
            except ValueError:
                return
            key = (hunter_id, treasure_id)
            smoothed = _smooth_rssi(key, hunter_rssi)
            state.update_hunter(hunter_id, treasure_id, smoothed)
            socketio.emit('rssi_update', {
                'hunter_id':   hunter_id,
                'treasure_id': treasure_id,
                'hunter_rssi': round(smoothed, 1),
                'relay_rssi':  relay_rssi,
            })

    # --- CLAIM:H<id> ---
    elif payload.startswith('CLAIM:'):
        parts = payload.split(':')
        if len(parts) == 2:
            hunter_id = parts[1]
            socketio.emit('claim', {'hunter_id': hunter_id})

    # --- FOUND:T<id>:H<id> ---
    elif payload.startswith('FOUND:'):
        parts = payload.split(':')
        if len(parts) == 3:
            treasure_id = parts[1]
            hunter_id   = parts[2]
            state.mark_found(treasure_id, hunter_id)
            socketio.emit('found', {
                'treasure_id': treasure_id,
                'hunter_id':   hunter_id,
            })


# ---------------------------------------------------------------------------
# Background reader thread
# ---------------------------------------------------------------------------
def start_reader(socketio, state):
    """Start the serial reader in a daemon thread."""
    t = threading.Thread(target=_reader_loop, args=(socketio, state), daemon=True)
    t.start()
    return t


def _reader_loop(socketio, state):
    global _connected, _last_error
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
                with _lock:
                    _connected  = True
                    _last_error = None
                socketio.emit('serial_status', get_status())

                while True:
                    raw = ser.readline()
                    if raw:
                        try:
                            line = raw.decode('utf-8', errors='replace')
                        except Exception:
                            line = ''
                        _parse_line(line, socketio, state)

        except serial.SerialException as exc:
            with _lock:
                _connected  = False
                _last_error = str(exc)
            socketio.emit('serial_status', get_status())
            time.sleep(3)

        except Exception as exc:
            with _lock:
                _connected  = False
                _last_error = str(exc)
            socketio.emit('serial_status', get_status())
            time.sleep(3)
