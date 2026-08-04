"""
diagnose_serial.py — Raw serial monitor for micro:bit debugging.
Run this INSTEAD of app.py to see exactly what the micro:bit sends.
Press Ctrl+C to stop.
"""
import serial
import time

PORT = "COM3"
BAUD = 115200

print(f"Opening {PORT} at {BAUD} baud...")
try:
    with serial.Serial(PORT, BAUD, timeout=2) as ser:
        print(f"Connected. Watching for data — press Ctrl+C to stop.\n")
        start = time.time()
        line_count = 0
        while True:
            raw = ser.readline()
            if raw:
                line = raw.decode("utf-8", errors="replace").strip()
                elapsed = time.time() - start
                line_count += 1
                print(f"[{elapsed:6.1f}s] #{line_count:04d}  {repr(line)}")
            else:
                # Timeout — no data received in 2 seconds
                elapsed = time.time() - start
                print(f"[{elapsed:6.1f}s]  *** no data received (2s timeout) ***")
except serial.SerialException as e:
    print(f"ERROR: {e}")
except KeyboardInterrupt:
    print("\nStopped.")
