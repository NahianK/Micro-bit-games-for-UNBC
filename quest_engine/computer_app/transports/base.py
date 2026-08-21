# base.py - the one interface the game engine talks to.
#
# WHY THIS LAYER EXISTS
# The engine never touches a serial port. It receives normalised messages and
# sends command lines, and that is the whole contract. Two future changes are
# the reason:
#
#   - Camera tracking. A tracker that works out where children are standing can
#     be wrapped as a Transport that emits synthetic answers, and no trial
#     logic, content pack or audio cue has to change.
#   - Bluetooth. Not possible today (MicroPython exposes no BLE, and BLE cannot
#     coexist with the radio module), but if that ever changes it slots in here.
#
# A Transport delivers messages as (message_dict, rssi) where message_dict is
# whatever protocol.parse_payload() produced, and rssi may be None.

class Transport(object):
    """Abstract two-way link to the wands."""

    name = 'transport'

    def start(self, on_message):
        """
        Begin delivering messages. on_message(message_dict, rssi) is called
        from a background thread, so implementations of it must be thread safe.
        """
        raise NotImplementedError

    def send_command(self, line):
        """Push one already-encoded command line. Returns True if it went out."""
        raise NotImplementedError

    def stop(self):
        """Stop delivering and release the underlying device."""
        raise NotImplementedError

    def status(self):
        """
        Connection state for the gamemaster console:
            {'connected': bool, 'target': str, 'error': str or None}
        """
        raise NotImplementedError
