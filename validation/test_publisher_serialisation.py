#!/usr/bin/env python3
"""
Network-free check that one publisher never runs two sends at once.

A publisher owns one TLS socket carrying one command stream. Two threads sending at the
same time interleave their writes and read each other's replies, which surfaces as
[SSL: WRONG_VERSION_NUMBER] or "Read on closed or unwrapped SSL socket" and leaves the
publisher wedged. Services really do share a publisher across threads: the policy engine
publishes from its heartbeat loop and from its admin callback, so its policy records to
the planner were being lost while its rule set looked correct everywhere else.

Run: PYTHONPATH=smart-route-planning-agent/src python validation/test_publisher_serialisation.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

from at_client.common import AtSign  # noqa: E402

from atsign.atsign_io import AtPublisher  # noqa: E402


def publisher_with(fake_send):
    """An AtPublisher with no network: __init__ would connect, so build it directly.

    This mirrors every field __init__ sets apart from the client itself; if a new one is
    added there, add it here too.
    """
    pub = AtPublisher.__new__(AtPublisher)
    pub.atsign = AtSign("@alpha")
    pub._root = "unused"
    pub._verbose = False
    pub._stale = False
    pub._failures = 0
    pub._send_lock = threading.Lock()
    pub.client = None
    pub._notify_once = fake_send
    return pub


def main():
    # 1. Concurrent callers must not overlap on the socket.
    in_flight = []
    overlaps = []
    order = []

    def one_send(to, key_name, value, namespace, ttl_ms):
        in_flight.append(to)
        if len(in_flight) > 1:
            overlaps.append(list(in_flight))
        time.sleep(0.15)
        order.append(to)
        in_flight.remove(to)
        return "delivered"

    pub = publisher_with(one_send)
    # The two callers the policy engine really has: a heartbeat and an admin callback.
    threads = [threading.Thread(target=pub.notify, args=(f"@peer{i}", "policy", "{}"),
                                kwargs={"deadline_s": 5.0})
               for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not overlaps, f"two sends shared the socket: {overlaps}"
    assert len(order) == 4, order
    print(f"4 concurrent sends -> serialised, no overlap ({' '.join(order)})")

    # 2. A caller that gives up waiting for the lock says so, and does not hang.
    holder_started = threading.Event()

    def slow_send(to, key_name, value, namespace, ttl_ms):
        holder_started.set()
        time.sleep(1.0)
        return "delivered"

    pub = publisher_with(slow_send)
    holder = threading.Thread(target=pub.notify, args=("@peer", "policy", "{}"),
                              kwargs={"deadline_s": 5.0})
    holder.start()
    assert holder_started.wait(5), "the first send never started"
    began = time.monotonic()
    try:
        pub.notify("@other", "policy", "{}", deadline_s=0.2)
        raise AssertionError("expected the second caller to time out waiting for the lock")
    except TimeoutError as e:
        assert "waited" in str(e), e
    waited = time.monotonic() - began
    assert waited < 1.0, f"the second caller blocked for {waited:.1f}s instead of its deadline"
    holder.join(5)
    print("contended send     -> times out on its own deadline, no hang")

    # 3. The lock is released even when a send raises, so one failure cannot wedge the
    #    publisher for every later caller — which is the failure this fix is about.
    def failing_send(to, key_name, value, namespace, ttl_ms):
        raise RuntimeError("[SSL: WRONG_VERSION_NUMBER] wrong version number")

    pub = publisher_with(failing_send)
    for _ in range(2):
        try:
            pub.notify("@peer", "policy", "{}", deadline_s=5.0)
            raise AssertionError("expected the send to raise")
        except RuntimeError:
            pass
    assert not pub._send_lock.locked(), "the lock was not released after a failed send"
    print("failed send        -> lock released, publisher still usable")

    print("\nPASS: a publisher's socket carries one send at a time.")


if __name__ == "__main__":
    main()
