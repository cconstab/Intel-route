#!/usr/bin/env python3
"""
Network-free check that the abandoned-read guard is in force.

If a command's reply is not fully read, that reply stays queued on the socket and the
NEXT command receives it — every command after that is one reply behind. This is worse
than an error, because a lookup can return a different record's value and succeed: we
could encrypt to the wrong recipient's shared key with nothing raising.

`atsign_io` therefore applies at_python PR #545's behaviour locally until it ships:
a connection whose read fails is discarded.
"""
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

import atsign.atsign_io  # noqa: F401,E402  — importing applies the guard
from at_client.connections.atconnection import AtConnection  # noqa: E402
from at_client.connections.atsecondaryconnection import AtSecondaryConnection  # noqa: E402


def _connection(read_side_effect):
    conn = AtSecondaryConnection.__new__(AtSecondaryConnection)
    conn._connected = True
    conn._verbose = False
    sock = MagicMock()
    sock.read.side_effect = read_side_effect
    conn._secure_root_socket = sock
    return conn


def main():
    assert getattr(AtConnection, "_discards_on_abandoned_read", False), "guard not applied"
    print("guard applied at import")

    # A read that fails must leave the connection unusable, so the queued reply can
    # never be handed to a later command.
    conn = _connection(TimeoutError("The read operation timed out"))
    try:
        conn.read()
        raise AssertionError("expected the timeout to propagate")
    except TimeoutError:
        pass
    assert conn.is_connected() is False, "connection was kept after an abandoned read"
    print("abandoned read   -> connection discarded, exception still raised")

    # A healthy read must be untouched.
    conn = _connection([b"data:ok\n"])
    assert conn.read() == "data:ok\n"
    assert conn.is_connected() is True
    print("successful read  -> connection kept, value returned unchanged")

    # Applying it twice must not stack wrappers.
    atsign.atsign_io._discard_connection_on_abandoned_read()
    conn = _connection([b"data:ok\n"])
    assert conn.read() == "data:ok\n"
    print("idempotent       -> re-applying changes nothing")

    print("\nPASS: a connection holding an unread reply is never reused.")


if __name__ == "__main__":
    main()
