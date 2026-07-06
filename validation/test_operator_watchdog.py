#!/usr/bin/env python3
"""
Network-free test of the operator console's silence-watchdog: it recreates the
subscriber only after prolonged silence, retiring the old one via stop().
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

import atsign.operator_console as oc  # noqa: E402


class FakeSub:
    def __init__(self, *a, **k):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True   # no network — return immediately

    def stop(self):
        self.stopped = True


def main():
    oc.AtSubscriber = FakeSub          # patch out the real (networking) subscriber
    oc.SILENCE_S = 45
    me = "@op"

    # 1. recent record -> no recreate
    oc._subscriber = FakeSub()
    oc._last_rx = time.monotonic()
    assert oc._watchdog_tick(me) is False
    print("recent traffic -> no recreate")

    # 2. silence past the threshold -> recreate + retire the old one
    old = FakeSub()
    oc._subscriber = old
    oc._last_rx = time.monotonic() - 100     # > SILENCE_S
    assert oc._watchdog_tick(me) is True
    time.sleep(0.3)                          # let the spawn thread run
    assert old.stopped is True, "old subscriber not stopped"
    assert oc._subscriber is not old, "subscriber not replaced"
    assert isinstance(oc._subscriber, FakeSub) and oc._subscriber.started
    print("silence -> old stopped, fresh subscriber started")

    # 3. an incoming planner record resets the silence timer
    oc._last_rx = time.monotonic() - 100
    payload = '{"optimal_route": "r.gpx", "rerouted": false, "points": []}'
    oc._on_record(oc.PLANNER, f"@op:status.{oc.roles.namespace()}{oc.PLANNER}", payload, {})
    assert time.monotonic() - oc._last_rx < 5, "record did not reset the watchdog timer"
    print("planner record -> silence timer reset")

    print("\nPASS: watchdog recreates only on silence and retires the wedged subscriber.")


if __name__ == "__main__":
    main()
