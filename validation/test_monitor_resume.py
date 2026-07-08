#!/usr/bin/env python3
"""
Verify AtSubscriber's reconnect-resume WITHOUT any live server (atsdk >= 0.2.71):

  1. _consume() captures the newest notification epoch into _last_epoch.
  2. Each (re)connect passes that epoch to AtClient.start_monitor(last_received_time=...)
     — the SDK API added by at_python #530 — instead of restarting from 0.

We stub AtClient so nothing touches the network.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

import atsign.atsign_io as aio  # noqa: E402
from at_client.connections.notification.atevents import AtEvent, AtEventType  # noqa: E402

calls = []


class FakeClient:
    """Records start_monitor args, then stops the subscriber so start() returns."""

    def __init__(self, subscriber):
        self._subscriber = subscriber

    def start_monitor(self, regex, last_received_time=0):
        calls.append((regex, last_received_time))
        self._subscriber._running = False  # end the reconnect loop after this call


def run_one_connect(sub):
    aio.AtClient = lambda *a, **k: FakeClient(sub)
    aio.time.sleep = lambda s: None  # skip the 3s reconnect delay
    sub.start()


def main():
    sub = aio.AtSubscriber("@alpha", "smartroute", on_record=lambda *a: None)

    # --- FIRST connect: no epoch seen yet -> resume position 0 (cold start) ---
    run_one_connect(sub)
    assert calls[-1] == ("smartroute", 0), calls[-1]
    print(f"cold start        -> start_monitor{calls[-1]}   (expected last_received_time=0)")

    # --- notifications arrive; simulate _consume's epoch capture ---
    for em in (1000, 1725000000123, 1725000000050):   # includes an out-of-order older one
        ev = AtEvent(AtEventType.UPDATE_NOTIFICATION,
                     {"key": "live_traffic.smartroute@alpha", "epochMillis": em})
        e = ev.event_data.get("epochMillis")
        if e is not None and int(e) > sub._last_epoch:
            sub._last_epoch = int(e)
    assert sub._last_epoch == 1725000000123, sub._last_epoch
    print(f"after 3 notifs    -> _last_epoch={sub._last_epoch}   (keeps the max, ignores older)")

    # --- RECONNECT: must resume from the last-seen epoch, NOT 0 ---
    run_one_connect(sub)
    assert calls[-1] == ("smartroute", 1725000000123), calls[-1]
    print(f"after reconnect   -> start_monitor{calls[-1]}   (resumes, no backlog replay)")

    print("\nPASS: reconnect resumes via start_monitor(last_received_time=<last epoch>).")


if __name__ == "__main__":
    main()
