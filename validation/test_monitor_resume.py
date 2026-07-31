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

    # --- FIRST connect: start from now, NOT 0. The SDK builds "monitor:0 <regex>"
    #     verbatim and the server answers that by replaying everything it retains, which
    #     made the policy engine re-apply every historical rule change on startup and the
    #     planner re-ingest old live_traffic. ---
    before = int(aio.time.time() * 1000)
    run_one_connect(sub)
    regex, epoch = calls[-1]
    assert regex == "smartroute", calls[-1]
    assert epoch != 0, "a cold start asked for the full retained backlog"
    assert before - aio.MONITOR_STARTUP_GRACE_MS - 5000 <= epoch <= before, (
        f"cold-start epoch {epoch} is not ~now minus the startup grace")
    print(f"cold start        -> start_monitor(smartroute, ~now)   (no backlog replay)")

    # Opting in still works, for a caller that genuinely wants the history.
    replaying = aio.AtSubscriber("@alpha", "smartroute", on_record=lambda *a: None,
                                 replay_backlog=True)
    assert replaying._last_epoch == 0, replaying._last_epoch
    print("replay_backlog=True -> epoch 0, the full backlog, when explicitly asked for")

    # --- notifications arrive; simulate _consume's epoch capture. Epochs are relative to
    #     the cold-start baseline, since anything older than it is deliberately ignored ---
    base = sub._last_epoch
    newest = base + 5000
    for em in (base + 1000, newest, base + 500):   # includes an out-of-order older one
        ev = AtEvent(AtEventType.UPDATE_NOTIFICATION,
                     {"key": "live_traffic.smartroute@alpha", "epochMillis": em})
        e = ev.event_data.get("epochMillis")
        if e is not None and int(e) > sub._last_epoch:
            sub._last_epoch = int(e)
    assert sub._last_epoch == newest, sub._last_epoch
    print(f"after 3 notifs    -> _last_epoch={sub._last_epoch}   (keeps the max, ignores older)")

    # --- RECONNECT: must resume from the last-seen epoch, NOT 0 ---
    run_one_connect(sub)
    assert calls[-1] == ("smartroute", newest), calls[-1]
    print(f"after reconnect   -> start_monitor{calls[-1]}   (resumes, no backlog replay)")

    print("\nPASS: reconnect resumes via start_monitor(last_received_time=<last epoch>).")


if __name__ == "__main__":
    main()
