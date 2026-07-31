#!/usr/bin/env python3
"""
Network-free check that a bad shared root connection cannot wedge a process forever.

`AtRootConnection` is a singleton and `AtConnection.__init__` resolves its address once,
keeping it in `_addr_info` for the life of the process. If the root server a process is
pinned to stops answering, every later client build fails inside `find_secondary` — before
`AtClient` assigns `secondary_connection`, which is why it surfaces as an AttributeError
from `__del__`. Rebuilding the client does not help, because the broken root connection is
shared, so publishers and subscribers retry forever and only a restart clears it.

Observed as: EOF occurred in violation of protocol -> "reconnect failed" -> "loop error",
repeating with no recovery.

Run: PYTHONPATH=smart-route-planning-agent/src python validation/test_root_connection_recovery.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

from at_client import AtClient  # noqa: E402
from at_client.common import AtSign  # noqa: E402
from at_client.connections.atrootconnection import AtRootConnection  # noqa: E402

import atsign.atsign_io as io  # noqa: E402

SINGLETON = "_AtRootConnection__instance"


class _SocketRaising:
    """A socket whose reads fail the way a dropped TLS peer does."""

    def __init__(self, error):
        self.error = error

    def read(self, *_args):
        raise self.error

    def close(self):
        pass


class DeadRoot:
    """A root connection pinned to an address that no longer answers."""

    def __init__(self):
        self.disconnected = False

    def disconnect(self):
        self.disconnected = True


def main():
    # 1. The singleton is actually cleared, and the dead connection is closed.
    dead = DeadRoot()
    setattr(AtRootConnection, SINGLETON, dead)
    io._reset_root_connection()
    assert getattr(AtRootConnection, SINGLETON) is None, "the singleton was not cleared"
    assert dead.disconnected, "the dead root connection was not closed"
    print("reset            -> singleton cleared, dead connection closed")

    # 2. Resetting when there is nothing to reset must not raise.
    io._reset_root_connection()
    print("reset when empty -> no error")

    # 3. A close() that throws must not stop the reset: the point is to drop the object.
    class Stubborn(DeadRoot):
        def disconnect(self):
            raise OSError("Bad file descriptor")

    setattr(AtRootConnection, SINGLETON, Stubborn())
    io._reset_root_connection()
    assert getattr(AtRootConnection, SINGLETON) is None, "a failing close blocked the reset"
    print("reset on a broken connection -> still cleared")

    # 4. The wedge itself: a build that fails while the root is poisoned must succeed on
    #    the retry once the root has been dropped — that is what turns "never recovers"
    #    into "recovers on the next cycle".
    setattr(AtRootConnection, SINGLETON, DeadRoot())
    attempts = []
    original = io.AtClient

    class FakeClient:
        def __init__(self, atsign, root_address=None, queue=None, verbose=False):
            attempts.append(getattr(AtRootConnection, SINGLETON))
            if len(attempts) == 1:
                # What a poisoned root produces: __init__ dies before it can assign
                # secondary_connection.
                raise ConnectionError("EOF occurred in violation of protocol (_ssl.c:2406)")
            self.secondary_connection = None

    io.AtClient = FakeClient
    try:
        io._bound_socket_reads = lambda client, seconds: None
        client = io._new_bounded_client(AtSign("@alpha"), "root.atsign.org:64")
    finally:
        io.AtClient = original

    assert len(attempts) == 2, f"expected one retry, saw {len(attempts)} attempt(s)"
    assert attempts[0] is not None, "the first attempt should have run with the stale root"
    assert attempts[1] is None, "the retry reused the poisoned root instead of redialling"
    assert client is not None
    print("poisoned root    -> build retried after dropping it, and succeeded")

    # 5. A failed build must not print an AttributeError from the collector: that noise
    #    made a recoverable retry look like a crash.
    assert getattr(AtClient, "_del_survives_failed_init", False), "the __del__ guard is not applied"
    broken = AtClient.__new__(AtClient)  # exactly what a failed __init__ leaves behind
    broken.__del__()  # must not raise
    print("failed build     -> collector stays quiet, no misleading traceback")

    # 6. A root connection whose greeting read fails must not claim to be connected.
    #    connect() sets _connected = True BEFORE reading the greeting, and find_secondary
    #    only redials `if not self.is_connected()`. So without the abandoned-read guard a
    #    failed greeting leaves a dead socket marked live, and every later lookup writes
    #    into it. The guard covers this because it wraps AtConnection.read itself; PR #545
    #    wraps only execute_command's read, so it would not.
    root = AtRootConnection.__new__(AtRootConnection)
    root._connected = True
    root._verbose = False
    root._secure_root_socket = _SocketRaising(ConnectionResetError("EOF in violation of protocol"))
    try:
        root.read()
        raise AssertionError("expected the greeting read to raise")
    except ConnectionResetError:
        pass
    assert root.is_connected() is False, (
        "a root connection with a failed greeting still claims to be connected, "
        "so find_secondary would never redial it")
    print("failed greeting  -> root marked disconnected, so the next lookup redials")

    print("\nPASS: a bad root connection is dropped, so a process recovers on its own.")


if __name__ == "__main__":
    main()
