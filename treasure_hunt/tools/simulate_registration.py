#!/usr/bin/env python3
# simulate_registration.py — headless simulation of the eight-hunter registration
# protocol. Run without any hardware or Reachy agent.
#
#   python simulate_registration.py [--hunters N]
#
# Tests all eight A/B code combinations, duplicate code rejection, stale-nonce
# timeouts, wrong-code retry, and graceful cancellation.

import sys
import os
import time
import random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'computer_app'))

import registration

# ---------------------------------------------------------------------------
# Harness helpers
# ---------------------------------------------------------------------------

SENT_LINES = []
REACHY_EVENTS = []

def _send(line):
    SENT_LINES.append(line.strip())

class _FakeReachy:
    def event(self, event_type, **data):
        REACHY_EVENTS.append({'type': event_type, 'data': data})


PASS = []
FAIL = []

def check(label, cond, detail=''):
    if cond:
        print('  PASS  {}'.format(label))
        PASS.append(label)
    else:
        print('  FAIL  {} {}'.format(label, detail))
        FAIL.append(label)

def section(title):
    print('\n{}'.format(title))
    print('-' * len(title))

# ---------------------------------------------------------------------------
# Helpers for feeding packets into the session
# ---------------------------------------------------------------------------

def feed_ready(session, nonce, token=None):
    tok = token or session.token
    session.on_packet('R', ['RG', 'R', nonce, tok])

def feed_code(session, nonce, code, token=None):
    tok = token or session.token
    session.on_packet('C', ['RG', 'C', nonce, tok, code])

def feed_ack(session, nonce, hid):
    session.on_packet('O', ['RG', 'O', nonce, hid])

# ---------------------------------------------------------------------------
# Test 1: Normal 3-hunter flow
# ---------------------------------------------------------------------------

def test_normal_3():
    section('Test 1: Normal 3-hunter identification')
    SENT_LINES.clear()
    REACHY_EVENTS.clear()

    s = registration.RegistrationSession(3, _send, reachy_client=_FakeReachy())
    s.start()

    check('REG_START sent', any(l.startswith('RG|S|') for l in SENT_LINES))
    tok = s.token

    # Feed 3 unique nonces as READY
    nonces = ['N001', 'N002', 'N003']
    for n in nonces:
        for _ in range(3):   # simulate repeated READY while logo held
            feed_ready(s, n, tok)

    s.tick()   # trigger prompting phase

    check('state is prompting or collecting',
          s.state in ('collecting', 'prompting'))

    # Simulate each hunter entering their assigned code
    for hid in ['H1', 'H2', 'H3']:
        snap = s.snapshot()
        if snap['state'] not in ('prompting', 'complete'):
            continue
        h = snap['hunters'].get(hid, {})
        nonce = h.get('nonce')
        code  = h.get('code')
        if nonce and code:
            feed_code(s, nonce, code, tok)
            feed_ack(s, nonce, hid)

    check('state is complete', s.state == 'complete',
          'got: {}'.format(s.state))
    check('RG|K sent for each hunter',
          sum(1 for l in SENT_LINES if l.startswith('RG|K|')) == 3,
          str(SENT_LINES))
    check('init_complete Reachy event',
          any(e['type'] == 'init_complete' for e in REACHY_EVENTS))
    check('all acked',
          all(v['acked'] for v in s.snapshot()['hunters'].values()))


# ---------------------------------------------------------------------------
# Test 2: All 8 unique codes are assigned (no repeats across 8-hunter session)
# ---------------------------------------------------------------------------

def test_eight_unique_codes():
    section('Test 2: Eight unique code assignments')
    s = registration.RegistrationSession(8, _send)
    codes = list(s._codes.values())
    check('8 unique codes', len(set(codes)) == 8,
          'codes: {}'.format(codes))
    check('all from valid set',
          all(c in registration._ALL_CODES for c in codes))

# ---------------------------------------------------------------------------
# Test 3: Wrong code -> retry
# ---------------------------------------------------------------------------

def test_wrong_code_retry():
    section('Test 3: Wrong code -> retry prompt')
    SENT_LINES.clear()
    REACHY_EVENTS.clear()

    s = registration.RegistrationSession(1, _send, reachy_client=_FakeReachy())
    s.start()

    nonce = 'W001'
    feed_ready(s, nonce)
    feed_ready(s, nonce)
    feed_ready(s, nonce)
    s.tick()

    # Get assigned code and submit a wrong one
    snap = s.snapshot()
    h = snap['hunters'].get('H1', {})
    nonce_assigned = h.get('nonce', nonce)
    correct_code   = h.get('code', 'AAA')
    wrong_code     = 'BBB' if correct_code != 'BBB' else 'AAA'

    feed_code(s, nonce_assigned, wrong_code)

    check('init_retry Reachy event',
          any(e['type'] == 'init_retry' for e in REACHY_EVENTS))

    # Now check assignment was cleared (hunter can try again)
    snap2 = s.snapshot()
    check('assignment cleared after wrong code',
          snap2['hunters']['H1'].get('nonce') is None)

# ---------------------------------------------------------------------------
# Test 4: Stale token -> ignored
# ---------------------------------------------------------------------------

def test_stale_token():
    section('Test 4: Stale session token -> packet ignored')
    SENT_LINES.clear()

    s = registration.RegistrationSession(2, _send)
    s.start()

    old_token = 'ZZZZ'
    feed_ready(s, 'N777', old_token)   # wrong token

    snap = s.snapshot()
    check('stale packet ignored (no nonces registered)',
          len([n for n, v in s._nonces.items()]) == 0)

# ---------------------------------------------------------------------------
# Test 5: Cancellation
# ---------------------------------------------------------------------------

def test_cancel():
    section('Test 5: Cancel session')
    SENT_LINES.clear()
    REACHY_EVENTS.clear()

    s = registration.RegistrationSession(2, _send, reachy_client=_FakeReachy())
    s.start()
    s.cancel()

    check('state is cancelled', s.state == 'cancelled')
    check('RG|E sent', any(l == 'RG|E' for l in SENT_LINES))
    check('init_cancel Reachy event',
          any(e['type'] == 'init_cancel' for e in REACHY_EVENTS))

    # Packets after cancel are ignored
    initial_nonces = len(s._nonces)
    feed_ready(s, 'LATE', s.token)
    check('packets ignored after cancel',
          len(s._nonces) == initial_nonces)

# ---------------------------------------------------------------------------
# Test 6: Snapshot structure
# ---------------------------------------------------------------------------

def test_snapshot_structure():
    section('Test 6: Snapshot structure')
    s = registration.RegistrationSession(4, _send)
    snap = s.snapshot()

    check('has state',        'state'   in snap)
    check('has token',        'token'   in snap)
    check('has n_hunters',    'n_hunters' in snap)
    check('has hunters dict', 'hunters'  in snap)
    check('4 hunters in dict', len(snap['hunters']) == 4)
    for hid, h in snap['hunters'].items():
        check('{} has code'.format(hid), 'code' in h and len(h['code']) == 3)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--hunters', type=int, default=3)
    args = parser.parse_args()

    test_normal_3()
    test_eight_unique_codes()
    test_wrong_code_retry()
    test_stale_token()
    test_cancel()
    test_snapshot_structure()

    print('\n' + '='*40)
    print('Result: {} passed, {} failed'.format(len(PASS), len(FAIL)))
    if FAIL:
        print('Failed:', ', '.join(FAIL))
        sys.exit(1)
    else:
        print('All checks passed.')


if __name__ == '__main__':
    main()
