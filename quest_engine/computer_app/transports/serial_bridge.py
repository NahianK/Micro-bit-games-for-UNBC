# serial_bridge.py - Transport over the USB-tethered bridge micro:bit.
#
# Reads lines in a daemon thread and reconnects on its own, so unplugging the
# micro:bit mid-session does not end the game.
#
# REUSE: the reconnect loop is the same shape as serial_reader.py in the other
# games in this repo. The difference is that this one also WRITES: nothing in
# pass_the_ball / hide_and_seek / treasure_hunt ever calls ser.write().

import threading
import time

import serial

import protocol as P
from transports.base import Transport


class SerialBridgeTransport(Transport):

    name = 'serial-bridge'

    def __init__(self, port, baud=115200, reconnect_delay=2.0):
        self.port = port
        self.baud = baud
        self.reconnect_delay = reconnect_delay

        self._serial = None
        self._write_lock = threading.Lock()
        self._stop = threading.Event()
        self._on_message = None
        self._thread = None

        self._connected = False
        self._error = None

    # -- Transport ---------------------------------------------------------
    def start(self, on_message):
        self._on_message = on_message
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        self._stop.set()

    def send_command(self, line):
        with self._write_lock:
            if self._serial is None:
                return False
            try:
                self._serial.write((line + '\n').encode('utf-8'))
                self._serial.flush()
                return True
            except Exception as exc:
                self._error = str(exc)
                return False

    def status(self):
        return {
            'connected': self._connected,
            'target': self.port,
            'error': self._error,
        }

    # -- internals ---------------------------------------------------------
    def _deliver(self, line):
        message, rssi = P.parse_serial_line(line)
        if message is None:
            return              # boot banner, partial line, radio noise
        if self._on_message is not None:
            self._on_message(message, rssi)

    def _loop(self):
        while not self._stop.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=1) as ser:
                    with self._write_lock:
                        self._serial = ser
                    self._connected = True
                    self._error = None

                    while not self._stop.is_set():
                        raw = ser.readline()
                        if not raw:
                            continue
                        line = raw.decode('utf-8', errors='replace').strip()
                        if line:
                            self._deliver(line)

            except serial.SerialException as exc:
                self._error = str(exc)
            except Exception as exc:
                self._error = str(exc)

            self._connected = False
            with self._write_lock:
                self._serial = None
            if not self._stop.is_set():
                time.sleep(self.reconnect_delay)
