#!/usr/bin/env python3
"""
Deterministic test of the first-contact shared-key pre-warm retry in AtSubscriber.

The atsdk drops a new sender's first notification when the sender's shared key
hasn't propagated yet (get_encryption_key_shared_by_other raises -> swallowed).
_ensure_shared_key retries that resolution so the record isn't lost. This test
forces the lookup to fail then succeed; no network involved.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

import atsign.atsign_io as aio
from at_client.connections.notification.atevents import AtEvent, AtEventType

KEY = "@alpha:live_traffic.smartroute@bravo"   # a shared-key notification key


class FakeClient:
    def __init__(self, fail_times):
        self.keys = {}          # empty -> not cached -> must resolve
        self.calls = 0
        self.fail_times = fail_times

    def get_encryption_key_shared_by_other(self, sk):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise Exception("shared key not on our server yet")
        self.keys[sk.get_shared_shared_key_name()] = "RESOLVED"
        return "RESOLVED"


def make_sub():
    sub = aio.AtSubscriber("@alpha", "smartroute", on_record=lambda *a: None)
    sub._key_backoff_s = 0.001   # keep the test fast
    sub._key_retries = 4
    return sub


def ev():
    return AtEvent(AtEventType.UPDATE_NOTIFICATION, {"key": KEY})


def main():
    # 1) fails twice, resolves on the 3rd attempt -> recovered, no exception
    sub, c = make_sub(), FakeClient(fail_times=2)
    sub._ensure_shared_key(c, ev())
    assert c.calls == 3, c.calls
    print(f"recovers after transient failures -> resolved on attempt {c.calls} (was dropped pre-fix)")

    # 2) never resolves -> gives up after _key_retries, still no exception raised
    sub, c = make_sub(), FakeClient(fail_times=99)
    sub._ensure_shared_key(c, ev())
    assert c.calls == sub._key_retries, c.calls
    print(f"gives up gracefully after {c.calls} tries (no crash, notification just skipped)")

    # 3) already cached -> no lookup at all (fast path, no overhead per notification)
    sub, c = make_sub(), FakeClient(fail_times=0)
    from at_client.common.keys import SharedKey
    c.keys[SharedKey.from_string(key=KEY).get_shared_shared_key_name()] = "CACHED"
    sub._ensure_shared_key(c, ev())
    assert c.calls == 0, c.calls
    print("cached shared key -> zero extra lookups (no per-record overhead once warm)")

    # 4) non-namespace key -> ignored
    sub, c = make_sub(), FakeClient(fail_times=0)
    sub._ensure_shared_key(c, AtEvent(AtEventType.UPDATE_NOTIFICATION, {"key": "@alpha:foo.other@bravo"}))
    assert c.calls == 0, c.calls
    print("out-of-namespace key -> ignored")

    print("\nPASS: first-contact retry recovers transient shared-key gaps deterministically.")


if __name__ == "__main__":
    main()
