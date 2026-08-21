#!/usr/bin/env python3
# challenge_console.py - Quest Engine bench harness.
#
# A plain terminal tool for typing challenges at the wands and watching the
# answers come back. No Flask, no audio, no story: this exists to prove the
# hardware loop and to tune the sensor thresholds before any of that matters.
#
# Run it from this directory:
#
#     python challenge_console.py --port COM3
#     python challenge_console.py --list          (show serial ports and exit)
#
# Then type challenges:
#
#     btna 3          press A three times, default window
#     clap 2 8000     clap twice, 8 second window
#     hold 3000       hold the logo for 3 seconds
#     point NE        point north-east (needs USE_COMPASS=True in mb_player.py)
#     mask 2          address player 2 only
#     mask all        address everybody again
#     demo            walk through every verb, one Enter press at a time
#     verbs           list the whole vocabulary
#     idle            tell the wands to stand down
#     quit
#
# Anything not recognised as a command is treated as a verb, so you can also
# just type "shake" and get sensible defaults.

import argparse
import sys
import threading
import time

try:
    from serial.tools import list_ports
except ImportError:
    sys.exit('pyserial is missing. Run:  pip install -r requirements.txt')

import config
import protocol as P
from transports import SerialBridgeTransport


# ===========================================================================
# Round tracking, so every challenge gets a verdict
# ===========================================================================
class Round(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.expected = set(P.ids_in_mask(cmd['mask']))
        self.answers = {}                  # player_id -> (result, ms)
        self.started = time.time()
        self.reported = False

    def deadline(self):
        return self.started + (self.cmd['win'] / 1000.0) + config.ANSWER_GRACE_S

    def summary(self):
        rows = []
        for pid in sorted(self.expected):
            if pid in self.answers:
                result, ms = self.answers[pid]
                if result == P.RESULT_OK:
                    rows.append('P{} {:.2f}s'.format(pid, ms / 1000.0))
                else:
                    rows.append('P{} {}'.format(
                        pid, P.RESULT_LABELS.get(result, result)))
            else:
                rows.append('P{} no answer'.format(pid))

        winners = sorted((ms, pid) for pid, (res, ms) in self.answers.items()
                         if res == P.RESULT_OK)
        fastest = '  fastest P{}'.format(winners[0][1]) if winners else ''
        return '   verdict: {}/{} done{}\n   {}'.format(
            len(winners), len(self.expected), fastest, '  '.join(rows))


# ===========================================================================
# Console
# ===========================================================================
class Console(object):
    def __init__(self, port):
        self.link = SerialBridgeTransport(port, config.BAUD_RATE)
        self.seq = 0
        self.mask = P.mask_for(range(1, config.ACTIVE_PLAYERS + 1))
        self.rounds = {}                   # seq -> Round
        self.seen_players = {}             # player_id -> last heartbeat time
        self.show_heartbeats = False
        self.show_beacons = False
        self._lock = threading.Lock()

    # -- incoming ----------------------------------------------------------
    def on_message(self, msg, rssi):
        kind = msg['kind']

        if kind == P.CMD:
            # The transport only sees a C| line when the bridge echoes one it
            # sent itself, which is how the standalone Button A walkthrough
            # shows up here. Those arrive with no rssi.
            print('\n[bridge sent] {}'.format(P.describe_command(msg)))
            with self._lock:
                if msg['seq'] not in self.rounds:
                    self.rounds[msg['seq']] = Round(msg)
                    self.seq = max(self.seq, msg['seq'])
            return

        if kind == P.ANSWER:
            with self._lock:
                known = msg['seq'] in self.rounds
                rnd = self.rounds.get(msg['seq'])
                if rnd is not None and msg['player_id'] not in rnd.answers:
                    rnd.answers[msg['player_id']] = (msg['result'], msg['ms'])
            label = P.RESULT_LABELS.get(msg['result'], msg['result'])
            print('\n  P{}  {:<24} {:.2f}s  rssi {}{}'.format(
                msg['player_id'], label, msg['ms'] / 1000.0, rssi,
                '' if known else '  (unknown seq)'))
            return

        if kind == P.HEARTBEAT:
            pid = msg['player_id']
            with self._lock:
                first = pid not in self.seen_players
                self.seen_players[pid] = time.time()
            if first:
                print('\n[roster] P{} is online'.format(pid))
            elif self.show_heartbeats:
                print('\n[hb] P{} seq={} {}'.format(pid, msg['seq'], msg['flags']))
            return

        if kind == P.BEACON and self.show_beacons:
            print('\n[beacon] {} rssi {}'.format(msg['prop_id'], rssi))

    def reap_rounds(self):
        """Print the verdict once a challenge window has fully elapsed."""
        while True:
            now = time.time()
            due = []
            with self._lock:
                for rnd in self.rounds.values():
                    if not rnd.reported and rnd.cmd['win'] and now >= rnd.deadline():
                        rnd.reported = True
                        due.append(rnd)
            for rnd in due:
                print('\n' + rnd.summary())
            time.sleep(0.2)

    # -- outgoing ----------------------------------------------------------
    def send_challenge(self, verb, arg=None, win=None):
        try:
            if verb == 'POINT' and arg is not None:
                arg = P.resolve_bearing(arg)
            line = P.encode_command(self.seq + 1, verb, arg, win, self.mask)
        except ValueError as exc:
            print('  ! {}'.format(exc))
            return None

        self.seq += 1
        cmd = P.parse_command(line)
        with self._lock:
            self.rounds[self.seq] = Round(cmd)

        if not self.link.send_command(line):
            print('  ! not connected ({})'.format(self.link.status()['error']))
            return None
        print('  -> {}'.format(P.describe_command(cmd)))
        return cmd

    # -- commands ----------------------------------------------------------
    def cmd_mask(self, args):
        if not args:
            print('  mask is {} (players {})'.format(
                self.mask, P.ids_in_mask(self.mask) or 'none'))
            return
        if args[0].lower() == 'all':
            self.mask = P.mask_for(range(1, config.ACTIVE_PLAYERS + 1))
        else:
            try:
                ids = [int(part) for chunk in args for part in chunk.split(',')
                       if part.strip()]
            except ValueError:
                print('  usage: mask all | mask 2 | mask 1,3,5')
                return
            self.mask = P.mask_for(ids)
        print('  mask -> players {}'.format(P.ids_in_mask(self.mask) or 'none'))

    def cmd_verbs(self):
        print('  {:<8} {:<9} {:<8} {:<15} {}'.format(
            'VERB', 'ARG', 'DEFAULT', 'SENSOR', 'MEANING'))
        for verb, kind, default, sensor, label in P.verb_help():
            print('  {:<8} {:<9} {:<8} {:<15} {}'.format(
                verb, kind, default, sensor, label))

    def cmd_demo(self):
        """
        One pass over every verb. Touches all five sensors, so a clean run is a
        full hardware check. POINT is left out because it needs the compass
        enabled and calibrated first.
        """
        script = [
            ('BTNA', 3), ('BTNB', 2),
            ('TILTL', 1), ('TILTR', 1), ('TILTU', 1), ('TILTD', 1),
            ('SHAKE', 2), ('FACEDN', 0), ('FACEUP', 0), ('BTNAB', 0),
            ('HOLD', 3000),
            ('CLAP', 2), ('SHOUT', 1000),
            ('LEVEL', 2000),
        ]
        print('  Enter sends each challenge, "s" skips, "q" stops.')
        for verb, arg in script:
            try:
                reply = input('  [{}] '.format(verb)).strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            if reply == 'q':
                break
            if reply == 's':
                continue
            self.send_challenge(verb, arg)
            time.sleep(0.2)
        self.send_challenge('IDLE')

    def cmd_status(self):
        state = self.link.status()
        print('  link {} on {}{}'.format(
            'up' if state['connected'] else 'DOWN', state['target'],
            '  ({})'.format(state['error']) if state['error'] else ''))
        with self._lock:
            seen = sorted(self.seen_players)
        print('  wands heard from: {}'.format(
            ', '.join('P{}'.format(p) for p in seen) or 'none yet'))

    # -- main --------------------------------------------------------------
    def run(self):
        self.link.start(self.on_message)
        threading.Thread(target=self.reap_rounds, daemon=True).start()
        print(HELP)

        while True:
            try:
                raw = input('> ').strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not raw:
                continue

            parts = raw.split()
            head, args = parts[0].lower(), parts[1:]

            if head in ('quit', 'exit', 'q'):
                break
            elif head in ('help', '?'):
                print(HELP)
            elif head == 'verbs':
                self.cmd_verbs()
            elif head == 'ports':
                show_ports()
            elif head == 'mask':
                self.cmd_mask(args)
            elif head == 'demo':
                self.cmd_demo()
            elif head == 'status':
                self.cmd_status()
            elif head == 'hb':
                self.show_heartbeats = not self.show_heartbeats
                print('  heartbeats {}'.format(
                    'shown' if self.show_heartbeats else 'hidden'))
            elif head == 'beacon':
                self.show_beacons = not self.show_beacons
                print('  beacons {}'.format(
                    'shown' if self.show_beacons else 'hidden'))
            elif head == 'raw':
                print('  -> {}'.format(
                    'sent' if self.link.send_command(' '.join(args)) else 'FAILED'))
            else:
                self.handle_verb(head, args)

        print('\nstanding the wands down...')
        self.send_challenge('IDLE')
        time.sleep(0.4)
        self.link.stop()

    def handle_verb(self, head, args):
        verb = head.upper()
        if verb not in P.VERBS:
            print('  unknown command or verb: {} (try "verbs")'.format(head))
            return

        arg = args[0] if args else None
        win = None
        if len(args) > 1:
            try:
                win = int(args[1])
            except ValueError:
                print('  window must be a whole number of milliseconds')
                return
        if arg is not None and verb != 'POINT':
            try:
                arg = int(arg)
            except ValueError:
                print('  arg must be a number for {}'.format(verb))
                return
        self.send_challenge(verb, arg, win)


HELP = """
Quest Engine bench console
  <verb> [arg] [window_ms]   send a challenge  (e.g. btna 3 / clap 2 8000)
  mask all | mask 1,3        choose who the next challenges address
  demo                       walk through every verb one at a time
  verbs                      list the vocabulary
  idle                       stand the wands down
  hb / beacon                toggle heartbeat and beacon chatter
  status | ports | help | quit
"""


def show_ports():
    found = list(list_ports.comports())
    if not found:
        print('  no serial ports found')
    for info in found:
        print('  {:<10} {}'.format(info.device, info.description))


def main():
    parser = argparse.ArgumentParser(description='Quest Engine bench console')
    parser.add_argument(
        '--port', default=config.SERIAL_PORT,
        help='serial port of the bridge micro:bit (config.py default: {})'.format(
            config.SERIAL_PORT))
    parser.add_argument('--list', action='store_true',
                        help='list serial ports and exit')
    opts = parser.parse_args()

    if opts.list:
        show_ports()
        return

    Console(opts.port).run()


if __name__ == '__main__':
    main()
