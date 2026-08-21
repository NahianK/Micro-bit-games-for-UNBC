# protocol.py - Quest Engine wire format.
#
# ONE source of truth for the four message shapes that travel over radio.
#
#   Downlink   C|<seq>|<verb>|<arg>|<win>|<mask>|<ack>
#   Answer     A|<pid>|<seq>|<result>|<ms>|<eid>
#   Heartbeat  H|<pid>|<seq>|<flags>
#   Beacon     B|<prop_id>
#
# The bridge relays every radio packet to USB as "<payload>,<rssi>".
#
# IMPORTANT: MicroPython on the micro:bit cannot import this module, so the
# firmware builds the same strings by hand with .format(). If you change a
# message shape here you MUST change microbit/mb_player.py, microbit/mb_prop.py
# and microbit/mb_bridge.py to match. The shapes are listed in a comment block
# at the top of each of those files for exactly this reason.
#
# Keep messages short - radio.config(length=64) is the ceiling and the default
# is 32 bytes. The longest command we generate is about 24 characters.

# ---------------------------------------------------------------------------
# Message kinds
# ---------------------------------------------------------------------------
CMD       = 'C'
ANSWER    = 'A'
HEARTBEAT = 'H'
BEACON    = 'B'

SEP = '|'

RESULT_OK   = 'OK'
RESULT_FAIL = 'FAIL'
# Sent instead of FAIL when a wand physically cannot attempt the challenge, so
# a room full of instant failures is not mistaken for a bug. Today the only
# cause is a POINT challenge on a wand whose compass is not calibrated.
RESULT_NOCAL = 'NOCAL'

RESULT_LABELS = {
    RESULT_OK:    'done',
    RESULT_FAIL:  'missed',
    RESULT_NOCAL: 'compass not calibrated',
}

# Wand states reported in the heartbeat flags field
FLAG_IDLE    = 'I'
FLAG_RESTING = 'R'
FLAG_ARMED   = 'A'
FLAG_DONE    = 'D'

MAX_PLAYERS      = 5
ALL_PLAYERS_MASK = (1 << MAX_PLAYERS) - 1      # 0b11111 == 31

# ---------------------------------------------------------------------------
# What the 'arg' field means, per verb
# ---------------------------------------------------------------------------
ARG_NONE    = 'none'        # arg ignored
ARG_COUNT   = 'count'       # do it this many times
ARG_MS      = 'ms'          # sustain it for this many milliseconds
ARG_BEARING = 'bearing'     # compass bearing in degrees, 0-359

# The firmware's entire vocabulary. 'window' is the default answer window in ms.
VERBS = {
    'BTNA':   {'arg': ARG_COUNT,   'default_arg': 3,    'window': 6000,
               'sensor': 'buttons',       'label': 'Press button A'},
    'BTNB':   {'arg': ARG_COUNT,   'default_arg': 2,    'window': 6000,
               'sensor': 'buttons',       'label': 'Press button B'},
    'BTNAB':  {'arg': ARG_NONE,    'default_arg': 0,    'window': 6000,
               'sensor': 'buttons',       'label': 'Press A and B together'},
    'TILTL':  {'arg': ARG_COUNT,   'default_arg': 1,    'window': 6000,
               'sensor': 'accelerometer', 'label': 'Tilt left'},
    'TILTR':  {'arg': ARG_COUNT,   'default_arg': 1,    'window': 6000,
               'sensor': 'accelerometer', 'label': 'Tilt right'},
    'TILTU':  {'arg': ARG_COUNT,   'default_arg': 1,    'window': 6000,
               'sensor': 'accelerometer', 'label': 'Tilt away from you'},
    'TILTD':  {'arg': ARG_COUNT,   'default_arg': 1,    'window': 6000,
               'sensor': 'accelerometer', 'label': 'Tilt towards you'},
    'SHAKE':  {'arg': ARG_COUNT,   'default_arg': 2,    'window': 6000,
               'sensor': 'accelerometer', 'label': 'Shake it'},
    'FACEUP': {'arg': ARG_NONE,    'default_arg': 0,    'window': 6000,
               'sensor': 'accelerometer', 'label': 'Turn it face up'},
    'FACEDN': {'arg': ARG_NONE,    'default_arg': 0,    'window': 6000,
               'sensor': 'accelerometer', 'label': 'Turn it face down'},
    'CLAP':   {'arg': ARG_COUNT,   'default_arg': 2,    'window': 8000,
               'sensor': 'microphone',    'label': 'Clap'},
    'SHOUT':  {'arg': ARG_MS,      'default_arg': 1000, 'window': 8000,
               'sensor': 'microphone',    'label': 'Shout and hold it'},
    'HOLD':   {'arg': ARG_MS,      'default_arg': 3000, 'window': 10000,
               'sensor': 'logo touch',    'label': 'Hold the logo'},
    'LEVEL':  {'arg': ARG_MS,      'default_arg': 2000, 'window': 12000,
               'sensor': 'accelerometer', 'label': 'Hold it level'},
    'POINT':  {'arg': ARG_BEARING, 'default_arg': 0,    'window': 15000,
               'sensor': 'compass',       'label': 'Point to a bearing'},
    'NEAR':   {'arg': ARG_NONE,    'default_arg': 0,    'window': 60000,
               'sensor': 'radio RSSI',    'label': 'Find the hidden beacon'},
    'IDLE':   {'arg': ARG_NONE,    'default_arg': 0,    'window': 0,
               'sensor': '-',             'label': 'Stand down'},
}

# Verbs whose progress is "n of m done" rather than "held for n ms"
COUNTABLE_VERBS = tuple(sorted(
    v for v in VERBS if VERBS[v]['arg'] == ARG_COUNT
))

# Verbs that need the microphone, so narration must duck while they are open
MIC_VERBS = ('CLAP', 'SHOUT')

# Compass rose, for narration that says "north-east" instead of "45 degrees"
BEARINGS = (
    ('N', 0), ('NE', 45), ('E', 90), ('SE', 135),
    ('S', 180), ('SW', 225), ('W', 270), ('NW', 315),
)
BEARING_BY_NAME = dict(BEARINGS)
NAME_BY_BEARING = dict((deg, name) for name, deg in BEARINGS)


# ---------------------------------------------------------------------------
# Player bitmask helpers
# ---------------------------------------------------------------------------
def mask_for(player_ids):
    """[1, 3] -> 0b00101 == 5."""
    mask = 0
    for pid in player_ids:
        if 1 <= pid <= MAX_PLAYERS:
            mask |= 1 << (pid - 1)
    return mask


def ids_in_mask(mask):
    """5 -> [1, 3]."""
    return [pid for pid in range(1, MAX_PLAYERS + 1) if mask & (1 << (pid - 1))]


def in_mask(mask, player_id):
    return bool(mask & (1 << (player_id - 1)))


def popcount(mask):
    n = 0
    while mask:
        mask &= mask - 1
        n += 1
    return n


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------
def encode_command(seq, verb, arg=None, win=None, mask=ALL_PLAYERS_MASK, ack=0):
    """Build a C| downlink line. Falls back to the verb's defaults."""
    verb = verb.upper()
    if verb not in VERBS:
        raise ValueError('unknown verb: {}'.format(verb))
    meta = VERBS[verb]
    if arg is None:
        arg = meta['default_arg']
    if win is None:
        win = meta['window']
    return SEP.join((
        CMD, str(int(seq)), verb, str(int(arg)),
        str(int(win)), str(int(mask)), str(int(ack)),
    ))


def resolve_bearing(value):
    """Accept 45, '45' or 'NE' and return degrees."""
    if isinstance(value, str):
        key = value.strip().upper()
        if key in BEARING_BY_NAME:
            return BEARING_BY_NAME[key]
    return int(value) % 360


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------
def split_serial_line(line):
    """
    Split a bridge line "<payload>,<rssi>" into (payload, rssi).

    The payload itself never contains a comma, but we split on the LAST comma
    anyway so a future payload change cannot silently corrupt the rssi.
    Returns (None, None) for blank lines, and (payload, None) when the line
    carries no rssi (which is how the bridge echoes its own downlink).
    """
    line = (line or '').strip()
    if not line:
        return None, None
    idx = line.rfind(',')
    if idx == -1:
        return line, None
    try:
        return line[:idx], int(line[idx + 1:])
    except ValueError:
        return line, None


def parse_command(payload):
    parts = payload.split(SEP)
    if len(parts) < 6 or parts[0] != CMD:
        return None
    try:
        return {
            'kind': CMD,
            'seq':  int(parts[1]),
            'verb': parts[2],
            'arg':  int(parts[3]),
            'win':  int(parts[4]),
            'mask': int(parts[5]),
            'ack':  int(parts[6]) if len(parts) > 6 else 0,
        }
    except ValueError:
        return None


def parse_answer(payload):
    parts = payload.split(SEP)
    if len(parts) < 5 or parts[0] != ANSWER:
        return None
    try:
        return {
            'kind':      ANSWER,
            'player_id': int(parts[1]),
            'seq':       int(parts[2]),
            'result':    parts[3],
            'ms':        int(parts[4]),
            'eid':       int(parts[5]) if len(parts) > 5 else 0,
        }
    except ValueError:
        return None


def parse_heartbeat(payload):
    parts = payload.split(SEP)
    if len(parts) < 4 or parts[0] != HEARTBEAT:
        return None
    try:
        return {
            'kind':      HEARTBEAT,
            'player_id': int(parts[1]),
            'seq':       int(parts[2]),
            'flags':     parts[3],
        }
    except ValueError:
        return None


def parse_beacon(payload):
    parts = payload.split(SEP)
    if len(parts) < 2 or parts[0] != BEACON:
        return None
    return {'kind': BEACON, 'prop_id': parts[1]}


_PARSERS = {
    CMD:       parse_command,
    ANSWER:    parse_answer,
    HEARTBEAT: parse_heartbeat,
    BEACON:    parse_beacon,
}


def parse_payload(payload):
    """Dispatch on the leading kind character. None if unrecognised."""
    if not payload:
        return None
    parser = _PARSERS.get(payload[0])
    if parser is None:
        return None
    return parser(payload)


def parse_serial_line(line):
    """
    Full path for one bridge line: returns (message_dict, rssi).
    message_dict is None for anything unparseable, so callers can ignore noise
    such as the boot banner without special-casing it.
    """
    payload, rssi = split_serial_line(line)
    if payload is None:
        return None, None
    return parse_payload(payload), rssi


# ---------------------------------------------------------------------------
# Human-readable helpers, used by the console and the gamemaster UI
# ---------------------------------------------------------------------------
def describe_command(cmd):
    """'BTNA x3 within 6.0s -> P1,P2,P3' for logs and the GM console."""
    verb = cmd['verb']
    meta = VERBS.get(verb, {})
    kind = meta.get('arg', ARG_NONE)

    if kind == ARG_COUNT:
        what = '{} x{}'.format(verb, cmd['arg'])
    elif kind == ARG_MS:
        what = '{} for {:.1f}s'.format(verb, cmd['arg'] / 1000.0)
    elif kind == ARG_BEARING:
        deg = cmd['arg'] % 360
        what = '{} {}deg{}'.format(
            verb, deg,
            ' (' + NAME_BY_BEARING[deg] + ')' if deg in NAME_BY_BEARING else '',
        )
    else:
        what = verb

    targets = ids_in_mask(cmd['mask'])
    who = ','.join('P{}'.format(p) for p in targets) if targets else 'nobody'
    if cmd['win']:
        return '{} within {:.1f}s -> {}'.format(what, cmd['win'] / 1000.0, who)
    return '{} -> {}'.format(what, who)


def verb_help():
    """Sorted (verb, arg_kind, default_arg, sensor, label) rows for help text."""
    rows = []
    for verb in sorted(VERBS):
        meta = VERBS[verb]
        rows.append((verb, meta['arg'], meta['default_arg'],
                     meta['sensor'], meta['label']))
    return rows
