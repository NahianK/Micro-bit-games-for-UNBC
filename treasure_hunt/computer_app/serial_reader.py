# serial_reader.py - Treasure Hunt FULL version
# Reads serial output from the dedicated bridge micro:bit (mb_bridge.py).
# Parses treasure hunt radio packets and emits SocketIO events.
# Also handles two-way communication: sends registration commands downward.

import threading
import time
from collections import deque

import serial
from config import SERIAL_PORT, BAUD_RATE, SMOOTH_WINDOW
import reachy_client

# ---------------------------------------------------------------------------
# Module-level state (thread-safe via _lock)
# ---------------------------------------------------------------------------
_connected  = False
_last_error = None
_lock       = threading.Lock()
_serial_obj = None            # open serial.Serial instance (or None)

# Smoothing buffers
_smooth_buffers = {}

# Write queue for downlink commands (PC → bridge → radio)
_write_queue = deque()
_write_lock  = threading.Lock()


def get_status():
    with _lock:
        return {
            'connected': _connected,
            'port':      SERIAL_PORT,
            'error':     _last_error,
        }


def send_line(line):
    """
    Queue a line to be written to the serial port (bridge downlink).
    Thread-safe; the reader loop flushes the queue on each iteration.
    """
    with _write_lock:
        _write_queue.append(line.strip() + '\n')


def signal_hunters_go(repeats=6, interval_s=0.25):
    """Broadcast RG|G so every hunter plays the game-start beep."""
    def _worker():
        for _ in range(repeats):
            send_line('RG|G')
            time.sleep(interval_s)

    threading.Thread(target=_worker, daemon=True).start()


def _smooth_rssi(key, new_val):
    buf = _smooth_buffers.setdefault(key, deque(maxlen=SMOOTH_WINDOW))
    buf.append(new_val)
    return sum(buf) / len(buf)


# ---------------------------------------------------------------------------
# Packet parsers
# ---------------------------------------------------------------------------

def _parse_line(raw_line, socketio, state, reg_callback):
    """
    Parse one comma-terminated serial line and emit SocketIO events.

    Line formats:
        TRS:T1,-72          → treasure T1 beacon
        HUNT:H1:T1:-65,-58  → hunter proximity
        CLAIM:H1,-45        → hunter Button B
        FOUND:T1:H1,-40     → confirmed find
        RG|R|nonce|tok,-60  → hunter READY (registration)
        RG|C|nonce|tok|code,-55 → hunter code entry
        RG|O|nonce|hid,-50  → hunter ACK binding
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

    # --- Registration uplink packets ---
    if payload.startswith('RG|'):
        parts = payload.split('|')
        rg_type = parts[1] if len(parts) > 1 else ''
        session = reg_callback() if reg_callback else None
        if session is not None:
            session.on_packet(rg_type, parts)
        return

    # --- TRS:T<id> ---
    if payload.startswith('TRS:'):
        parts = payload.split(':')
        if len(parts) == 2:
            state.update_treasure_signal(parts[1], relay_rssi)
            socketio.emit('treasure_signal', {
                'treasure_id': parts[1],
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
            smoothed = _smooth_rssi((hunter_id, treasure_id), hunter_rssi)
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
            if getattr(state, 'use_reachy', False):
                reachy_client.event('claim', hunter_id=hunter_id)

    # --- FOUND:T<id>:H<id> ---
    elif payload.startswith('FOUND:'):
        parts = payload.split(':')
        if len(parts) == 3:
            treasure_id = parts[1]
            hunter_id   = parts[2]
            if state.game_over:
                return
            state.mark_found(treasure_id, hunter_id)
            socketio.emit('found', {
                'treasure_id': treasure_id,
                'hunter_id':   hunter_id,
            })
            # Narration only — scoring already happened in mark_found above.
            if getattr(state, 'use_reachy', False):
                reachy_client.event('found',
                                    hunter_id=hunter_id,
                                    treasure_id=treasure_id)
            if state.is_game_over() and not state.game_over:
                state.game_over = True
                lb = state.get_leaderboard()
                # Determine winner for Reachy
                winner_id = lb[0]['hunter_id'] if lb else None
                is_tie = (len(lb) > 1 and lb[0]['finds'] == lb[1]['finds'])
                socketio.emit('game_over', {
                    'leaderboard':     lb,
                    'total_treasures': len(state.active_treasures),
                })
                if getattr(state, 'use_reachy', False):
                    reachy_client.event('game_over',
                                        winner_id=winner_id,
                                        is_tie=is_tie,
                                        total=len(state.active_treasures))


# ---------------------------------------------------------------------------
# Background reader thread
# ---------------------------------------------------------------------------

def start_reader(socketio, state, reg_callback=None):
    """Start the serial reader in a daemon thread."""
    t = threading.Thread(
        target=_reader_loop,
        args=(socketio, state, reg_callback),
        daemon=True)
    t.start()
    return t


def _reader_loop(socketio, state, reg_callback):
    global _connected, _last_error, _serial_obj
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
                _serial_obj = ser
                with _lock:
                    _connected  = True
                    _last_error = None
                socketio.emit('serial_status', get_status())

                while True:
                    # --- Downlink flush ---
                    with _write_lock:
                        while _write_queue:
                            line = _write_queue.popleft()
                            try:
                                ser.write(line.encode('utf-8'))
                            except Exception:
                                pass

                    # --- Uplink read ---
                    raw = ser.readline()
                    if raw:
                        try:
                            line = raw.decode('utf-8', errors='replace')
                        except Exception:
                            line = ''
                        _parse_line(line, socketio, state, reg_callback)

        except serial.SerialException as exc:
            _serial_obj = None
            with _lock:
                _connected  = False
                _last_error = str(exc)
            socketio.emit('serial_status', get_status())
            time.sleep(3)

        except Exception as exc:
            _serial_obj = None
            with _lock:
                _connected  = False
                _last_error = str(exc)
            socketio.emit('serial_status', get_status())
            time.sleep(3)
