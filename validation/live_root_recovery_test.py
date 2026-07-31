#!/usr/bin/env python3
"""
Prove the root-recovery path against a REAL atServer, without waiting for an outage.

The wedge this checks: `AtRootConnection` is a process-wide singleton whose address is
resolved once, so when the root server a process is pinned to stops answering, every later
client build fails in `find_secondary` and only a restart clears it. That is rare and
environmental, so rather than waiting for it, this poisons the live singleton — pointing it
at a port nothing listens on — and then asks for a client.

Expected: the first build fails, `_new_bounded_client` drops the shared root connection,
redials, and the second build succeeds and authenticates for real.

Without the fix the second build fails exactly like the first, which is what "no self
healing at all" looked like in production.

Run on a machine that has the atSign's keys:

    cd ~/Intel-route
    export ATSIGN_PROFILE=vanity
    PYTHONPATH=smart-route-planning-agent/src \\
      python validation/live_root_recovery_test.py            # defaults to the planner
    PYTHONPATH=smart-route-planning-agent/src \\
      python validation/live_root_recovery_test.py @some_atsign
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

from at_client.common import AtSign  # noqa: E402
from at_client.connections.atrootconnection import AtRootConnection  # noqa: E402

from atsign import roles  # noqa: E402
from atsign.atsign_io import _new_bounded_client  # noqa: E402

SINGLETON = "_AtRootConnection__instance"
# Refused rather than black-holed: a closed port fails immediately, where an unroutable
# address would sit in the TCP handshake for a minute or more.
DEAD_ADDRESS = ("127.0.0.1", 1)


def root_singleton():
    return getattr(AtRootConnection, SINGLETON, None)


def main():
    atsign = sys.argv[1] if len(sys.argv) > 1 else roles.atsign_for("planner")
    root = roles.root()
    print(f"atSign {atsign}  root {root}  profile {os.environ.get('ATSIGN_PROFILE', 'ee')}\n")

    print("1. build a client normally (baseline — needs keys and a reachable root)")
    client = _new_bounded_client(AtSign(atsign), root)
    assert client is not None
    healthy = root_singleton()
    assert healthy is not None, "no root connection was created; nothing to poison"
    print(f"   ok — root connection {healthy!r}\n")

    print(f"2. poison it: point the shared root connection at {DEAD_ADDRESS[0]}:{DEAD_ADDRESS[1]}")
    try:
        healthy.disconnect()
    except Exception:
        pass
    healthy._addr_info = DEAD_ADDRESS
    healthy._connected = False
    print("   the next lookup through this singleton must fail\n")

    print("3. ask for another client — this is what a publisher's rebuild does")
    recovered = _new_bounded_client(AtSign(atsign), root)
    assert recovered is not None, "the rebuild failed: the fix did not recover the root"

    now = root_singleton()
    assert now is not healthy, (
        "the poisoned root connection is still in place — the build must have reused it, "
        "which is the wedge this test exists to catch")
    assert getattr(now, "_addr_info", None) != DEAD_ADDRESS, "the dead address survived"
    print(f"   recovered — root connection is now {now!r}")
    print(f"   redialled {getattr(now, '_host', '?')}:{getattr(now, '_port', '?')}\n")

    print("PASS: a poisoned root connection is dropped and redialled, so a long-running")
    print("      process recovers on its own instead of needing a restart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
