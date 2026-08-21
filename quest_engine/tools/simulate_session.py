#!/usr/bin/env python3
# simulate_session.py - run a whole scenario with no hardware and no audio.
#
#     python tools/simulate_session.py
#     python tools/simulate_session.py --pack space --fail-rate 0.4
#
# This wires the real Engine to a fake Transport whose wands answer by
# themselves, so you can check that a content pack actually plays through:
# every step reached, retries firing, "who": "random" addressing one child,
# and steps that need hardware you have not enabled being skipped rather than
# failing.
#
# Use it after editing a pack, before you gather five children in a room.
#
# It proves nothing about the physical game - not radio range, not whether the
# microphone threshold suits your PA. Only that the scenario logic holds.

import argparse
import os
import random
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, os.pardir, 'computer_app'))
sys.path.insert(0, APP)
os.chdir(APP)                       # engine loads packs/ relative to here

import config                                          # noqa: E402
import protocol as P                                   # noqa: E402
from engine import Engine, validate_pack, pack_line_ids  # noqa: E402
from transports.base import Transport                  # noqa: E402

# Keep the run brisk: the engine waits this long after a challenge closes for
# late radio packets, which we do not have.
config.ANSWER_GRACE_S = 0.05


class StubAudio(object):
    """Stands in for audio.Audio. Records the script instead of speaking it."""

    def __init__(self, pack_id, quiet=False):
        self.pack_id = pack_id
        self.quiet = quiet
        self.spoken = []

    def say(self, line_id, text='', wait=True, stop_event=None):
        self.spoken.append(line_id)
        if text and not self.quiet:
            print('    narrator: {}'.format(text))

    def sfx(self, name, wait=False, stop_event=None):
        pass

    def go_quiet(self, lead=None):
        pass

    def stop(self):
        pass

    def is_talking(self):
        return False

    def missing_lines(self, line_ids):
        return list(line_ids)

    def describe(self):
        return 'stub audio'


class FakeTransport(Transport):
    """
    Wands that answer on their own.

    Mimics the two behaviours that matter: the bridge acknowledging answers is
    irrelevant here, but the reaction delay and the chance of a child missing
    the challenge entirely are what shake out the scoring rules.
    """

    name = 'fake'

    def __init__(self, players, fail_rate=0.0, silent_rate=0.0):
        self.players = players
        self.fail_rate = fail_rate
        self.silent_rate = silent_rate
        self.commands = []
        self._on_message = None
        self._stop = threading.Event()

    def start(self, on_message):
        self._on_message = on_message
        threading.Thread(target=self._heartbeats, daemon=True).start()

    def stop(self):
        self._stop.set()

    def status(self):
        return {'connected': True, 'target': 'simulated', 'error': None}

    def send_command(self, line):
        cmd = P.parse_command(line)
        if cmd is None:
            return False
        self.commands.append(cmd)
        if cmd['verb'] != 'IDLE':
            threading.Thread(target=self._answer, args=(cmd,), daemon=True).start()
        return True

    def _heartbeats(self):
        while not self._stop.is_set():
            for pid in self.players:
                self._on_message(
                    {'kind': P.HEARTBEAT, 'player_id': pid, 'seq': 0,
                     'flags': 'I'}, -60)
            time.sleep(0.3)

    def _answer(self, cmd):
        for pid in P.ids_in_mask(cmd['mask']):
            if random.random() < self.silent_rate:
                continue                    # flat battery / child not listening
            delay = random.uniform(0.02, 0.12)
            time.sleep(delay)
            failed = random.random() < self.fail_rate
            self._on_message({
                'kind': P.ANSWER,
                'player_id': pid,
                'seq': cmd['seq'],
                'result': P.RESULT_FAIL if failed else P.RESULT_OK,
                'ms': cmd['win'] if failed else int(delay * 1000) + 200,
                'eid': 1,
            }, -62)


FAILURES = []


def check(label, condition, detail=''):
    if condition:
        print('  PASS  {}'.format(label))
    else:
        FAILURES.append(label)
        print('  FAIL  {}{}'.format(label, '  <- ' + detail if detail else ''))


def check_packs():
    print('\nvalidating packs')
    for pack_id in Engine.available_packs():
        import json
        with open(os.path.join('packs', '{}.json'.format(pack_id)),
                  encoding='utf-8') as handle:
            pack = json.load(handle)
        problems = validate_pack(pack)
        check('{} is valid'.format(pack_id), not problems,
              '; '.join(problems))

        ids = pack_line_ids(pack)
        check('{} line ids are unique'.format(pack_id),
              len(ids) == len(set(ids)),
              'duplicates: {}'.format(
                  sorted(set(i for i in ids if ids.count(i) > 1))))

        verbs = set(s['verb'].upper() for s in pack['steps']
                    if s.get('type') == 'challenge')
        sensors = set(P.VERBS[v]['sensor'] for v in verbs)
        print('      {} uses {} verbs across {} sensors: {}'.format(
            pack_id, len(verbs), len(sensors), ', '.join(sorted(sensors))))
        check('{} exercises every sensor'.format(pack_id), len(sensors) >= 5,
              'only {}'.format(sorted(sensors)))


def run_pack(pack_id, fail_rate, silent_rate, quiet):
    print('\nrunning pack "{}" (fail rate {:.0%}, silent rate {:.0%})'.format(
        pack_id, fail_rate, silent_rate))

    players = list(range(1, config.ACTIVE_PLAYERS + 1))
    transport = FakeTransport(players, fail_rate, silent_rate)
    audio_boxes = {}

    def audio_factory(pid):
        audio_boxes[pid] = StubAudio(pid, quiet=quiet)
        return audio_boxes[pid]

    config.PACK = pack_id
    engine = Engine(transport, audio_factory)
    transport.start(engine.on_message)
    time.sleep(0.4)                     # let the roster fill from heartbeats

    check('roster picked up all {} wands'.format(len(players)),
          engine.online_players() == players,
          str(engine.online_players()))

    total_steps = len(engine.pack['steps'])
    engine.start()

    deadline = time.time() + 90
    while engine.status == 'running' and time.time() < deadline:
        time.sleep(0.1)

    check('scenario finished', engine.status == 'finished', engine.status)

    snapshot = engine.snapshot()
    skipped = [s['id'] for s in engine.pack['steps'] if s.get('requires')]
    challenges = [s for s in engine.pack['steps']
                  if s.get('type') == 'challenge' and not s.get('requires')]

    spoken = audio_boxes[pack_id].spoken
    check('every runnable challenge was narrated',
          all(s['id'] in spoken for s in challenges),
          'missing: {}'.format([s['id'] for s in challenges
                                if s['id'] not in spoken]))

    check('hardware-gated steps were skipped, not failed',
          all(sid not in spoken for sid in skipped),
          'these ran anyway: {}'.format([s for s in skipped if s in spoken]))
    print('      skipped {} step(s) needing optional hardware: {}'.format(
        len(skipped), ', '.join(skipped) or 'none'))

    scored = snapshot['scores']
    check('scores were recorded for every wand',
          len(scored) == len(players), str(sorted(scored)))

    solo = [c for c in transport.commands if P.popcount(c['mask']) == 1
            and c['verb'] != 'IDLE']
    check('the "who: random" step addressed exactly one child',
          len(solo) >= 1, 'no single-player command was sent')

    check('every command fits in a radio packet',
          all(len(P.encode_command(c['seq'], c['verb'], c['arg'], c['win'],
                                   c['mask'], 31)) <= 32
              for c in transport.commands),
          'a command exceeded 32 bytes')

    print('      {} commands sent, {} steps in pack'.format(
        len(transport.commands), total_steps))
    for pid in sorted(scored, key=int):
        tally = scored[pid]
        best = '{:.2f}s'.format(tally['best_ms'] / 1000.0) \
            if tally['best_ms'] else '-'
        print('      P{}: {} passed, {} failed, best {}'.format(
            pid, tally['passed'], tally['failed'], best))

    engine.stop()
    transport.stop()


def main():
    parser = argparse.ArgumentParser(
        description='Run a Quest Engine scenario with simulated wands')
    parser.add_argument('--pack', default=None,
                        help='pack to run (default: all of them)')
    parser.add_argument('--fail-rate', type=float, default=0.25,
                        help='chance a child muffs a challenge (default 0.25)')
    parser.add_argument('--silent-rate', type=float, default=0.05,
                        help='chance a wand does not answer at all')
    parser.add_argument('--verbose', action='store_true',
                        help='print the narration script as it plays')
    opts = parser.parse_args()

    random.seed(7)
    print('Quest Engine scenario simulation')
    print('(logic only - nothing here tests radio, microphones or children)')

    check_packs()
    for pack_id in ([opts.pack] if opts.pack else Engine.available_packs()):
        run_pack(pack_id, opts.fail_rate, opts.silent_rate,
                 quiet=not opts.verbose)

    print('')
    if FAILURES:
        print('{} check(s) failed:'.format(len(FAILURES)))
        for name in FAILURES:
            print('  - {}'.format(name))
        return 1
    print('All checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
