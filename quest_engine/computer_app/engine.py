# engine.py - runs a scenario: narrate, challenge, score, repeat.
#
# The engine knows nothing about serial ports or audio formats. It talks to a
# Transport (see transports/base.py) and an Audio object, which is what makes
# camera tracking a drop-in addition later rather than a rewrite.
#
# ONE STEP OF A SCENARIO
#   1. Read the instruction aloud.
#   2. If the challenge uses the microphone, go silent first - otherwise the
#      wands hear the narrator and score it as a clap.
#   3. Send the challenge once. The bridge handles repeating it.
#   4. Collect answers until everyone has replied or the window closes.
#   5. Score it, read the outcome aloud, and move on or retry.
#
# Threading: the scenario runs on one worker thread. Answers arrive on the
# transport's reader thread. Everything shared sits behind self._lock.
#
# The optional Reachy Mini (see robot.py) is told when a challenge opens and
# how it went, purely so it can react. It is never asked anything and it never
# answers: results come from the wands over radio and from nowhere else. When
# no robot is present the calls below land on a no-op object.

import json
import os
import random
import threading
import time
from collections import deque

import config
import protocol as P
from robot import Robot

PACKS_DIR = 'packs'

STATUS_IDLE     = 'idle'
STATUS_RUNNING  = 'running'
STATUS_PAUSED   = 'paused'
STATUS_FINISHED = 'finished'


class Round(object):
    """One open challenge and the answers gathered so far."""

    def __init__(self, cmd, step_id):
        self.cmd = cmd
        self.step_id = step_id
        self.expected = set(P.ids_in_mask(cmd['mask']))
        self.answers = {}                       # player_id -> (result, ms)
        self.started = time.time()
        self.closes_at = self.started + (cmd['win'] / 1000.0)

    def record(self, player_id, result, ms):
        if player_id in self.expected and player_id not in self.answers:
            self.answers[player_id] = (result, ms)

    def complete(self):
        return set(self.answers) >= self.expected

    def winners(self):
        """Players who succeeded, fastest first."""
        return [pid for _, pid in sorted(
            (ms, pid) for pid, (res, ms) in self.answers.items()
            if res == P.RESULT_OK)]

    def as_dict(self):
        return {
            'step_id': self.step_id,
            'verb': self.cmd['verb'],
            'arg': self.cmd['arg'],
            'description': P.describe_command(self.cmd),
            'expected': sorted(self.expected),
            'answers': dict((str(pid), {'result': res, 'ms': ms})
                            for pid, (res, ms) in self.answers.items()),
            'remaining_s': max(0.0, round(self.closes_at - time.time(), 1)),
            'winners': self.winners(),
        }


class Engine(object):

    def __init__(self, transport, audio_factory, on_update=None, robot=None):
        self.transport = transport
        # A factory, because the Audio object is bound to a pack and the
        # gamemaster can switch packs between sessions.
        self._audio_factory = audio_factory
        self.audio = None
        # A disabled Robot is a working object whose methods all do nothing, so
        # the scenario code below never has to ask whether one is attached.
        self.robot = robot if robot is not None else Robot(enabled=False)
        self.on_update = on_update or (lambda snapshot: None)

        self.pack = None
        self.pack_id = None
        self.difficulty = config.DIFFICULTY
        self.status = STATUS_IDLE
        self.step_index = -1

        self._seq = 0
        self._round = None
        self._roster = {}                       # player_id -> heartbeat info
        self._scores = {}                       # player_id -> tallies
        self._log = deque(maxlen=200)
        self._lock = threading.RLock()

        self._worker = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._skip = threading.Event()
        self._override = None                   # 'pass' or 'fail'

        self.load_pack(config.PACK)

    # =======================================================================
    # Packs
    # =======================================================================
    def load_pack(self, pack_id):
        path = os.path.join(PACKS_DIR, '{}.json'.format(pack_id))
        with open(path, encoding='utf-8') as handle:
            pack = json.load(handle)

        problems = validate_pack(pack)
        if problems:
            raise ValueError('{} is not valid:\n  {}'.format(
                path, '\n  '.join(problems)))

        with self._lock:
            self.pack = pack
            self.pack_id = pack_id
            self.audio = self._audio_factory(pack_id)
            self.step_index = -1
            self.status = STATUS_IDLE
        self.note('loaded pack "{}" - {} steps'.format(
            pack.get('title', pack_id), len(pack['steps'])))
        self._preload_voices(pack)
        return pack

    def _preload_voices(self, pack):
        """
        Push this pack's narration to the robot, in the background.

        Sending sixty short files takes a few seconds and there is no reason
        for the gamemaster's browser to sit through it. Doing it now is what
        stops the first airing of each line stalling mid-session.
        """
        audio = self.audio
        if audio is None:
            return

        def work():
            try:
                sent = audio.preload(pack_line_ids(pack))
            except Exception as exc:
                self.note('could not preload narration to the robot: {}'.format(exc))
                return
            if sent:
                self.note('{} narration line(s) ready on the robot'.format(sent))
                self._emit()

        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def available_packs():
        if not os.path.isdir(PACKS_DIR):
            return []
        return sorted(name[:-5] for name in os.listdir(PACKS_DIR)
                      if name.endswith('.json'))

    def missing_voice_lines(self):
        """Line ids with no WAV yet, so the console can warn before a session."""
        if self.pack is None or self.audio is None:
            return []
        return self.audio.missing_lines(pack_line_ids(self.pack))

    # =======================================================================
    # Incoming messages
    # =======================================================================
    def on_message(self, msg, rssi):
        kind = msg['kind']

        if kind == P.HEARTBEAT:
            with self._lock:
                entry = self._roster.setdefault(msg['player_id'], {})
                entry['last_seen'] = time.time()
                entry['flags'] = msg['flags']
                entry['seq'] = msg['seq']
                entry['rssi'] = rssi
            return

        if kind == P.ANSWER:
            with self._lock:
                # A heartbeat is not the only proof of life; an answer counts too.
                entry = self._roster.setdefault(msg['player_id'], {})
                entry['last_seen'] = time.time()
                if self._round is not None and msg['seq'] == self._round.cmd['seq']:
                    fresh = msg['player_id'] not in self._round.answers
                    self._round.record(msg['player_id'], msg['result'], msg['ms'])
                    if fresh:
                        label = P.RESULT_LABELS.get(msg['result'], msg['result'])
                        self.note('P{} {} ({:.2f}s)'.format(
                            msg['player_id'], label, msg['ms'] / 1000.0))
            self._emit()
            return

    def online_players(self):
        cutoff = time.time() - config.PLAYER_TIMEOUT_S
        with self._lock:
            return sorted(pid for pid, info in self._roster.items()
                          if info.get('last_seen', 0) >= cutoff
                          and 1 <= pid <= config.ACTIVE_PLAYERS)

    def _target_mask(self, who='all'):
        """
        Who a challenge is addressed to.

        Defaults to the wands we have actually heard from, not to the configured
        headcount. If a battery dies mid-session the round is scored against the
        children who are still holding a working wand, instead of failing
        everyone for a device that is not there.
        """
        online = self.online_players()
        if not online:
            online = list(range(1, config.ACTIVE_PLAYERS + 1))

        if who == 'random':
            return P.mask_for([random.choice(online)])
        if isinstance(who, list):
            wanted = [pid for pid in who if pid in online] or online
            return P.mask_for(wanted)
        return P.mask_for(online)

    # =======================================================================
    # Controls
    # =======================================================================
    def start(self, from_index=0):
        with self._lock:
            if self.status == STATUS_RUNNING:
                return False
            if self.status == STATUS_PAUSED:
                self.resume()
                return True
            self._scores = {}
            self.status = STATUS_RUNNING

        self._stop.clear()
        self._pause.clear()
        self._skip.clear()
        self._override = None
        self._worker = threading.Thread(
            target=self._run, args=(from_index,), daemon=True)
        self._worker.start()
        self.note('scenario started')
        return True

    def stop(self):
        self._stop.set()
        self._skip.set()
        if self.audio is not None:
            self.audio.stop()
        self.robot.release()
        self.robot.express('neutral')
        with self._lock:
            self.status = STATUS_IDLE
            self._round = None
        self.send_idle()
        self.note('stopped')
        self._emit()

    def pause(self):
        self._pause.set()
        with self._lock:
            if self.status == STATUS_RUNNING:
                self.status = STATUS_PAUSED
        self.note('paused - takes effect at the end of this step')
        self._emit()

    def resume(self):
        self._pause.clear()
        with self._lock:
            if self.status == STATUS_PAUSED:
                self.status = STATUS_RUNNING
        self.note('resumed')
        self._emit()

    def skip(self):
        """Abandon the open challenge and move to the next step."""
        self._skip.set()
        self.note('skipped')

    def override(self, result):
        """Force the open challenge to pass or fail. result is 'pass' or 'fail'."""
        self._override = 'pass' if result == 'pass' else 'fail'
        self._skip.set()
        self.note('gamemaster forced a {}'.format(self._override))

    def set_difficulty(self, level):
        if level in config.DIFFICULTY_WINDOW_SCALE:
            self.difficulty = level
            self.note('difficulty -> {}'.format(level))
            self._emit()

    def send_idle(self):
        """Stand the wands down."""
        with self._lock:
            self._seq += 1
            seq = self._seq
        self.transport.send_command(
            P.encode_command(seq, 'IDLE', mask=P.ALL_PLAYERS_MASK))

    def send_manual(self, verb, arg=None, win=None, who='all'):
        """
        Fire a one-off challenge outside the scenario. The gamemaster console
        uses this to improvise, and it is handy for warming children up.
        """
        verb = verb.upper()
        if verb not in P.VERBS:
            return None
        if verb == 'POINT' and arg is not None:
            arg = P.resolve_bearing(arg)
        mask = self._target_mask(who)
        with self._lock:
            self._seq += 1
            seq = self._seq
            line = P.encode_command(seq, verb, arg, win, mask)
            cmd = P.parse_command(line)
            self._round = Round(cmd, 'manual')
        self.transport.send_command(line)
        self.note('manual: {}'.format(P.describe_command(cmd)))
        self._emit()
        return cmd

    # =======================================================================
    # The scenario worker
    # =======================================================================
    def _run(self, from_index):
        steps = self.pack['steps']
        index = from_index

        while index < len(steps) and not self._stop.is_set():
            # Pausing lands between steps, never mid-challenge: freezing a
            # half-finished challenge would just confuse the children holding it.
            while self._pause.is_set() and not self._stop.is_set():
                time.sleep(0.2)
            if self._stop.is_set():
                break

            step = steps[index]

            # Steps can declare optional hardware. Skipping beats handing the
            # children a challenge their wands physically cannot answer.
            missing = unmet_requirement(step)
            if missing:
                self.note('skipping "{}" - needs {} (see config.py)'.format(
                    step.get('id'), missing))
                index += 1
                continue

            with self._lock:
                self.step_index = index
            self._emit()

            try:
                if step.get('type') == 'challenge':
                    self._run_challenge(step)
                else:
                    self._run_say(step)
            except Exception as exc:
                self.note('step "{}" failed: {}'.format(step.get('id'), exc))

            index += 1

        with self._lock:
            self._round = None
            if not self._stop.is_set():
                self.status = STATUS_FINISHED
                self.step_index = len(steps)
        if not self._stop.is_set():
            self.send_idle()
            self.note('scenario finished')
        self._emit()

    def _run_say(self, step):
        if step.get('sfx'):
            self.audio.sfx(step['sfx'])
        self.audio.say(step['id'], step.get('say', ''), stop_event=self._stop)

    def _run_challenge(self, step):
        verb = step['verb'].upper()
        arg = step.get('arg')
        if verb == 'POINT' and arg is not None:
            arg = P.resolve_bearing(arg)

        base_win = step.get('win') or P.VERBS[verb]['window']
        scale = config.DIFFICULTY_WINDOW_SCALE.get(self.difficulty, 1.0)
        win = max(1000, int(base_win * scale))

        attempts = max(1, int(step.get('attempts', 1)))
        require = step.get('require', 'all')

        for attempt in range(attempts):
            if self._stop.is_set():
                return

            line_id = step['id'] if attempt == 0 else '{}__again'.format(step['id'])
            text = step.get('say', '') if attempt == 0 else step.get(
                'say_again', step.get('say', ''))

            if step.get('sfx') and attempt == 0:
                self.audio.sfx(step['sfx'])
            self.audio.say(line_id, text, stop_event=self._stop)

            # A beat of body language as the window opens, so the children get
            # a visual "go" as well as an audible one.
            self.robot.express('listen')

            if verb in P.MIC_VERBS:
                # The wands would otherwise hear the narrator as a clap. They
                # hear servo noise just as well, so the robot freezes too.
                self.robot.hold_still()
                self.audio.go_quiet()

            try:
                passed = self._open_round(step, verb, arg, win, require)
            finally:
                self.robot.release()

            self.robot.express('pass' if passed else 'fail')

            if passed:
                self.audio.say('{}__pass'.format(step['id']),
                               step.get('on_pass', ''), stop_event=self._stop)
                if step.get('sfx_pass'):
                    self.audio.sfx(step['sfx_pass'])
                return

            last = (attempt == attempts - 1)
            self.audio.say('{}__fail'.format(step['id']),
                           step.get('on_fail', ''), stop_event=self._stop)
            if last and step.get('sfx_fail'):
                self.audio.sfx(step['sfx_fail'])

    def _open_round(self, step, verb, arg, win, require):
        mask = self._target_mask(step.get('who', 'all'))
        with self._lock:
            self._seq += 1
            seq = self._seq
            line = P.encode_command(seq, verb, arg, win, mask)
            cmd = P.parse_command(line)
            self._round = Round(cmd, step['id'])

        self._skip.clear()
        self._override = None

        if not self.transport.send_command(line):
            self.note('could not send the challenge - is the bridge plugged in?')

        self.note('challenge: {}'.format(P.describe_command(cmd)))
        self._emit()

        deadline = time.time() + (win / 1000.0) + config.ANSWER_GRACE_S
        while time.time() < deadline:
            if self._stop.is_set() or self._skip.is_set():
                break
            with self._lock:
                done = self._round.complete()
            if done:
                # Everyone has replied; no reason to sit out the rest of the clock.
                time.sleep(config.ANSWER_GRACE_S)
                break
            time.sleep(0.05)

        with self._lock:
            rnd = self._round
            passed = evaluate(rnd, require)
            if self._override == 'pass':
                passed = True
            elif self._override == 'fail':
                passed = False
            self._record_scores(rnd)

        self.note('{} -> {}'.format(step['id'], 'PASS' if passed else 'FAIL'))
        self._emit()
        return passed

    def _record_scores(self, rnd):
        for pid in rnd.expected:
            tally = self._scores.setdefault(
                pid, {'passed': 0, 'failed': 0, 'best_ms': None, 'total_ms': 0})
            answer = rnd.answers.get(pid)
            if answer and answer[0] == P.RESULT_OK:
                tally['passed'] += 1
                tally['total_ms'] += answer[1]
                if tally['best_ms'] is None or answer[1] < tally['best_ms']:
                    tally['best_ms'] = answer[1]
            else:
                tally['failed'] += 1

    # =======================================================================
    # Reporting
    # =======================================================================
    def note(self, text):
        stamp = time.strftime('%H:%M:%S')
        with self._lock:
            self._log.appendleft('{}  {}'.format(stamp, text))

    def _emit(self):
        try:
            self.on_update(self.snapshot())
        except Exception:
            pass                # a broken UI must never stall the scenario

    def snapshot(self):
        with self._lock:
            steps = self.pack['steps'] if self.pack else []
            step = None
            if 0 <= self.step_index < len(steps):
                current = steps[self.step_index]
                step = {
                    'id': current.get('id'),
                    'type': current.get('type', 'say'),
                    'say': current.get('say', ''),
                    'verb': current.get('verb'),
                    'whiteboard': current.get('whiteboard', ''),
                }
            cutoff = time.time() - config.PLAYER_TIMEOUT_S
            roster = {}
            for pid in range(1, config.ACTIVE_PLAYERS + 1):
                info = self._roster.get(pid, {})
                last = info.get('last_seen')
                roster[str(pid)] = {
                    'online': bool(last and last >= cutoff),
                    'flags': info.get('flags', '-'),
                    'rssi': info.get('rssi'),
                    'ago': round(time.time() - last, 1) if last else None,
                }
            return {
                'status': self.status,
                'pack': self.pack_id,
                'title': self.pack.get('title') if self.pack else None,
                'packs': self.available_packs(),
                'difficulty': self.difficulty,
                'step_index': self.step_index,
                'step_total': len(steps),
                'step': step,
                'round': self._round.as_dict() if self._round else None,
                'roster': roster,
                'scores': dict((str(k), v) for k, v in self._scores.items()),
                'link': self.transport.status(),
                'audio': self.audio.describe() if self.audio else 'no pack',
                'robot': self.robot.describe(),
                'log': list(self._log)[:40],
            }


# ===========================================================================
# Optional hardware
# ===========================================================================
# Which config flag gates each "requires" value a step can declare.
CAPABILITY_FLAGS = {
    'compass': 'USE_COMPASS',
    'prop': 'USE_PROP',
}


def unmet_requirement(step):
    """Return the requirement name if a step cannot run, else None."""
    need = step.get('requires')
    if not need:
        return None
    flag = CAPABILITY_FLAGS.get(need)
    if flag is None:
        return need                     # unknown requirement: skip, do not guess
    return None if getattr(config, flag, False) else need


# ===========================================================================
# Scoring rules
# ===========================================================================
def evaluate(rnd, require):
    """
    Did the group pass? 'require' is one of:
        'all'       every addressed child succeeded
        'any'       at least one did
        'majority'  more than half did
        <int>       at least this many did
    """
    if rnd is None:
        return False
    needed = len(rnd.expected)
    if needed == 0:
        return False
    got = len(rnd.winners())

    if require == 'any':
        return got >= 1
    if require == 'majority':
        return got * 2 > needed
    if isinstance(require, int):
        return got >= min(require, needed)
    return got >= needed


# ===========================================================================
# Pack validation. Better to refuse a broken pack at load than to discover a
# typo halfway through a session with a room full of children.
# ===========================================================================
def validate_pack(pack):
    problems = []
    if not isinstance(pack, dict):
        return ['pack is not a JSON object']

    steps = pack.get('steps')
    if not isinstance(steps, list) or not steps:
        return ['pack has no "steps" list']

    seen = set()
    for i, step in enumerate(steps):
        where = 'step {}'.format(i)
        if not isinstance(step, dict):
            problems.append('{} is not an object'.format(where))
            continue

        step_id = step.get('id')
        if not step_id:
            problems.append('{} has no "id"'.format(where))
        elif step_id in seen:
            problems.append('{} reuses the id "{}"'.format(where, step_id))
        else:
            seen.add(step_id)
            where = 'step "{}"'.format(step_id)

        kind = step.get('type', 'say')
        if kind not in ('say', 'challenge'):
            problems.append('{} has unknown type "{}"'.format(where, kind))

        if kind == 'challenge':
            verb = (step.get('verb') or '').upper()
            if verb not in P.VERBS:
                problems.append('{} has unknown verb "{}"'.format(
                    where, step.get('verb')))
            elif verb == 'IDLE':
                problems.append('{} uses IDLE as a challenge'.format(where))

            require = step.get('require', 'all')
            if not (isinstance(require, int)
                    or require in ('all', 'any', 'majority')):
                problems.append('{} has unknown require "{}"'.format(
                    where, require))

            who = step.get('who', 'all')
            if not (who in ('all', 'random') or isinstance(who, list)):
                problems.append('{} has unknown who "{}"'.format(where, who))

        need = step.get('requires')
        if need and need not in CAPABILITY_FLAGS:
            problems.append('{} requires unknown hardware "{}" (known: {})'.format(
                where, need, ', '.join(sorted(CAPABILITY_FLAGS))))

    return problems


def pack_lines(pack):
    """
    Every narration line a pack can ask for, as (line_id, text) in play order.

    This is the single source of truth for what tools/build_voice.py has to
    render. The naming rule is: the step id for the instruction, then the same
    id with __pass, __fail or __again appended for the follow-ups.
    """
    lines = []
    for step in pack.get('steps', []):
        step_id = step.get('id')
        if not step_id:
            continue
        lines.append((step_id, step.get('say', '')))
        if step.get('type') != 'challenge':
            continue
        for suffix, field in (('__again', 'say_again'),
                              ('__pass', 'on_pass'),
                              ('__fail', 'on_fail')):
            text = step.get(field)
            if text:
                lines.append(('{}{}'.format(step_id, suffix), text))
    return lines


def pack_line_ids(pack):
    """Just the ids from pack_lines(), for checking which WAVs are missing."""
    return [line_id for line_id, _ in pack_lines(pack)]
