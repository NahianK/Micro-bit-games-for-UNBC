# registration.py — PC-side state machine for eight-hunter identification.
#
# When Reachy Mini is enabled, each hunter micro:bit (V2) is assigned a random
# three-button code (A/B sequences) before gameplay starts. This module manages
# the full session lifecycle.
#
# PROTOCOL (serial packets via mb_bridge)
#
#   PC → bridge → radio (downlink):
#     RG|S|<tok>             Session start; hunters enter registration mode
#     RG|A|<nonce>|<tok>|<code>   Assign code to a specific nonce
#     RG|K|<nonce>|<hid>         Confirm assignment (nonce → H1..H8)
#     RG|E                       End/cancel session
#
#   radio → bridge → PC (uplink, comma + RSSI suffix stripped by serial_reader):
#     RG|R|<nonce>|<tok>          Hunter is ready (logo touched once, latched)
#     RG|C|<nonce>|<tok>|<code>   Hunter entered their code
#     RG|O|<nonce>|<hid>          Hunter acknowledged assignment
#
# STATES:  idle → collecting → prompting → complete | cancelled
#
# The SocketIO `reg_snapshot` event carries the full session state so the
# initialize.html page can render progress without polling.

import random
import string
import time

_ALL_CODES = ['AAA', 'AAB', 'ABA', 'ABB', 'BAA', 'BAB', 'BBA', 'BBB']
_READY_TIMEOUT_S   = 60.0   # max time waiting for all hunters to go ready
_ASSIGN_TIMEOUT_S  = 30.0   # max time for a hunter to enter their code
_NONCE_FRESH_S     = 1.5    # used only for display / late joiners
_K_RETRY_INTERVAL_S = 0.4   # re-broadcast RG|K until hunter ACKs
_K_RETRY_MAX        = 15


def _random_token(n=4):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))


def _assign_codes(n):
    """Return {H1: 'ABA', H2: 'BBB', ...} with random unique codes."""
    pool = random.sample(_ALL_CODES, k=n)
    return {'H{}'.format(i + 1): pool[i] for i in range(n)}


class RegistrationSession:
    """
    Manages one player-identification session.

    Thread-safety: the serial_reader thread calls on_packet() while the
    Flask/SocketIO thread may call snapshot() or cancel().  All mutations
    hold _lock.
    """

    def __init__(self, n_hunters, send_serial, reachy_client=None, socketio=None):
        """
        n_hunters   — how many hunters the game host expects (1-8)
        send_serial — callable(line) that writes a line to the bridge serial port
        reachy_client — optional ReachyClient; may be None
        socketio    — optional SocketIO instance for reg_snapshot pushes
        """
        self._n = min(max(1, n_hunters), 8)
        self._send = send_serial
        self._reachy = reachy_client
        self._sio = socketio

        self.token = _random_token()
        self._codes = _assign_codes(self._n)        # {hid: code}
        self._assignments = {hid: {'code': code, 'nonce': None, 'acked': False}
                             for hid, code in self._codes.items()}

        # nonce → {last_seen, hid (or None), latched, code_submitted (or None)}
        self._nonces = {}
        # nonce → {hid, last_sent, retries} — pending RG|K until RG|O received
        self._pending_k = {}

        self.state = 'collecting'   # collecting | prompting | complete | cancelled
        self._started_at = time.time()
        self._last_start_rebroadcast = 0.0
        self._current_prompt_hid = None   # which H# we are currently prompting
        self._current_prompt_deadline = None

        import threading
        self._lock = threading.RLock()   # re-entrant: tick/_push/snapshot can nest

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def start(self):
        """Send REG_START over serial and optionally tell Reachy."""
        self._send('RG|S|{}'.format(self.token))
        if self._reachy:
            self._reachy.event('init_open')
        self._push()

    def cancel(self):
        """Abort the session; serial bridge returns to normal mode."""
        with self._lock:
            self.state = 'cancelled'
        self._send('RG|E')
        if self._reachy:
            self._reachy.event('init_cancel')
        self._push()

    # -----------------------------------------------------------------------
    # Packet handling (called from serial_reader thread)
    # -----------------------------------------------------------------------

    def on_packet(self, packet_type, parts):
        """
        Dispatch one uplink registration packet.
        parts is the list from splitting the full payload on '|',
        e.g. ['RG', 'R', 'A1B2', 'ABCD'] for a READY packet.
        """
        if self.state in ('complete', 'cancelled'):
            return

        with self._lock:
            if packet_type == 'R':
                self._on_ready(parts)
            elif packet_type == 'C':
                self._on_code(parts)
            elif packet_type == 'O':
                self._on_ack(parts)

        self._push()

    def _on_ready(self, parts):
        """RG|R|<nonce>|<tok>"""
        if len(parts) < 4:
            return
        nonce = parts[2]
        tok   = parts[3]
        if tok != self.token:
            return
        now = time.time()
        entry = self._nonces.setdefault(nonce, {'last_seen': 0, 'hid': None,
                                                 'latched': False,
                                                 'code_submitted': None})
        entry['last_seen'] = now
        entry['latched'] = True   # one logo touch latches until assigned+acked

        # If all hunters have latched, move to prompting phase
        if self.state == 'collecting':
            self._check_all_ready()

    def _latched_unassigned(self):
        """Nonces that touched logo once and are not yet bound to an H#."""
        return [n for n, v in self._nonces.items()
                if v.get('latched') and v['hid'] is None]

    def _check_all_ready(self):
        latched = self._latched_unassigned()
        still_needed = self._n - len([a for a in self._assignments.values() if a['nonce']])
        if len(latched) >= still_needed and still_needed > 0:
            if self._reachy:
                self._reachy.event('init_all_ready')
            self.state = 'prompting'
            self._prompt_next()
        else:
            missing = self._n - len(latched)
            if missing > 0 and self._reachy:
                self._reachy.event('init_missing', missing=missing)

    def _prompt_next(self):
        """Find the next unacknowledged H# and send its ASSIGN."""
        for hid, data in self._assignments.items():
            if data['nonce'] is None:
                # Pick the first fresh nonce not yet assigned
                for nonce, ndata in self._nonces.items():
                    if ndata['hid'] is None and ndata.get('latched'):
                        data['nonce'] = nonce
                        ndata['hid'] = hid
                        self._current_prompt_hid = hid
                        self._current_prompt_deadline = time.time() + _ASSIGN_TIMEOUT_S
                        self._send('RG|A|{}|{}|{}'.format(
                            nonce, self.token, data['code']))
                        if self._reachy:
                            self._reachy.event('init_prompt',
                                               hunter_id=hid, code=data['code'])
                        return
                # No fresh nonce — stay in prompting, will retry when READY arrives
                return
        # All hunters assigned and prompted — waiting for ACKs
        self._check_complete()

    def _on_code(self, parts):
        """RG|C|<nonce>|<tok>|<entered>"""
        if len(parts) < 5:
            return
        nonce   = parts[2]
        tok     = parts[3]
        entered = parts[4].upper()
        if tok != self.token:
            return
        if nonce not in self._nonces:
            return

        hid = self._nonces[nonce]['hid']
        if hid is None:
            return

        expected = self._assignments[hid]['code']
        if entered == expected:
            self._send_confirm(nonce, hid)
            if self._reachy:
                self._reachy.event('init_confirm', hunter_id=hid)
        else:
            # Wrong code — invalidate assignment so the hunter must re-enter
            self._pending_k.pop(nonce, None)
            self._assignments[hid]['nonce'] = None
            self._nonces[nonce]['hid'] = None
            self._nonces[nonce]['last_seen'] = 0   # force staleness
            self._current_prompt_hid = None
            self._current_prompt_deadline = None
            if self._reachy:
                self._reachy.event('init_retry')
            self._prompt_next()

    def _on_ack(self, parts):
        """RG|O|<nonce>|<hid>"""
        if len(parts) < 4:
            return
        nonce = parts[2]
        hid   = parts[3]
        if nonce not in self._nonces:
            return
        if self._assignments.get(hid, {}).get('nonce') != nonce:
            return
        self._assignments[hid]['acked'] = True
        self._pending_k.pop(nonce, None)
        if not self._check_complete():
            # Advance: prompt the next unassigned hunter
            self._current_prompt_hid = None
            self._current_prompt_deadline = None
            self._prompt_next()

    def _send_confirm(self, nonce, hid):
        """Send RG|K and queue retries until the hunter sends RG|O."""
        self._send('RG|K|{}|{}'.format(nonce, hid))
        self._pending_k[nonce] = {
            'hid': hid, 'last_sent': time.time(), 'retries': 0,
        }

    def _retry_pending_k(self):
        now = time.time()
        for nonce, pk in list(self._pending_k.items()):
            hid = pk['hid']
            if self._assignments.get(hid, {}).get('acked'):
                del self._pending_k[nonce]
                continue
            if now - pk['last_sent'] >= _K_RETRY_INTERVAL_S and \
                    pk['retries'] < _K_RETRY_MAX:
                self._send('RG|K|{}|{}'.format(nonce, hid))
                pk['last_sent'] = now
                pk['retries'] += 1

    def _check_complete(self):
        if all(v['acked'] for v in self._assignments.values()):
            self.state = 'complete'
            self._send('RG|E')   # tells bridge/hunters session is over
            if self._reachy:
                self._reachy.event('init_complete')
            return True
        return False

    # -----------------------------------------------------------------------
    # Timeout polling (called by app.py background thread or route handlers)
    # -----------------------------------------------------------------------

    def tick(self):
        """
        Call periodically (e.g. every 500 ms) to handle timeouts.
        Returns True if the session is still active.
        """
        if self.state in ('complete', 'cancelled'):
            return False

        now = time.time()
        _need_push = False
        with self._lock:
            self._retry_pending_k()

            # Overall collection timeout
            if self.state == 'collecting' and \
                    now - self._started_at > _READY_TIMEOUT_S:
                self.state = 'cancelled'
                self._send('RG|E')
                if self._reachy:
                    self._reachy.event('init_cancel')
                _need_push = True

            # Re-broadcast REG_START so hunters that missed the first packet
            # (or powered on late) still enter READY and can read the logo.
            elif self.state == 'collecting':
                if now - self._last_start_rebroadcast >= 2.0:
                    self._last_start_rebroadcast = now
                    self._send('RG|S|{}'.format(self.token))

            # Per-hunter code entry timeout — re-prompt
            elif self.state == 'prompting' and \
                    self._current_prompt_deadline and \
                    now > self._current_prompt_deadline and \
                    self._current_prompt_hid:
                hid = self._current_prompt_hid
                nonce = self._assignments[hid]['nonce']
                if nonce:
                    self._pending_k.pop(nonce, None)
                    self._nonces[nonce]['hid'] = None
                self._assignments[hid]['nonce'] = None
                self._current_prompt_hid = None
                self._current_prompt_deadline = None
                if self._reachy:
                    self._reachy.event('init_retry')
                self._prompt_next()
                _need_push = True

        # Push snapshot AFTER releasing the lock — avoids RLock re-entry
        if _need_push:
            self._push()
        elif self.state == 'cancelled':
            return False

        return self.state not in ('complete', 'cancelled')

    # -----------------------------------------------------------------------
    # Snapshot for SocketIO / dashboard
    # -----------------------------------------------------------------------

    def snapshot(self):
        with self._lock:
            now = time.time()
            hunters = {}
            for hid, data in self._assignments.items():
                nonce = data['nonce']
                hunters[hid] = {
                    'hid':    hid,
                    'code':   data['code'],
                    'nonce':  nonce,
                    'acked':  data['acked'],
                    'ready':  (nonce is not None
                               and self._nonces.get(nonce, {}).get('hid') == hid),
                }
            n_ready = len(self._latched_unassigned())
            return {
                'state':            self.state,
                'token':            self.token,
                'n_hunters':        self._n,
                'hunters':          hunters,
                'fresh_unassigned': n_ready,
                'current_prompt':   self._current_prompt_hid,
            }

    def _push(self):
        if self._sio:
            try:
                self._sio.emit('reg_snapshot', self.snapshot())
            except Exception:
                pass
