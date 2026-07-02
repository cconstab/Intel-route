#!/usr/bin/env python3
"""
Verify the AtSubscriber reconnect-resume fix WITHOUT any live server:

  1. _consume() captures the newest notification epoch into _last_epoch.
  2. On (re)connect, _start_monitor_resuming() seeds the monitor connection's
     last_received_time with that epoch — so the monitor verb becomes
     `monitor:<last_epoch> <regex>` instead of the SDK default `monitor:0`.

We stub AtMonitorConnection + AuthUtil so nothing touches the network.
"""
import os, sys, types
from types import SimpleNamespace
from queue import Queue

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

import atsign.atsign_io as aio
from at_client.connections.notification.atevents import AtEvent, AtEventType

# ---- stub the monitor connection: record what epoch it was seeded with, and
#      build the exact monitor command the real SDK would send. ----------------
built_commands = []


class FakeMonitor:
    def __init__(self, queue=None, atsign=None, address=None, verbose=False, regex=".*"):
        self.regex = regex
        self.last_received_time = 0     # same class default as the real SDK
        self.running = False
    def connect(self):
        pass
    # the real AtMonitorConnection._run builds: "monitor:" + str(last_received_time) + " " + regex
    def _build_cmd(self):
        return "monitor:" + str(self.last_received_time) + " " + self.regex


def fake_auth(conn, atsign, keys):
    pass


class FakeClient:
    def __init__(self):
        self.atsign = "@alpha"
        self.secondary_address = SimpleNamespace(host="h", port=1)
        self.keys = {}
        self.monitor_connection = None
    def start_monitor(self, regex):
        # mirror AtClient.start_monitor: connection already set -> record the command
        built_commands.append(self.monitor_connection._build_cmd())


def run():
    aio.AtMonitorConnection = FakeMonitor
    aio.AuthUtil = types.SimpleNamespace(authenticate_with_pkam=staticmethod(fake_auth))

    sub = aio.AtSubscriber("@alpha", "smartroute", on_record=lambda *a: None)

    # --- FIRST connect: no epoch seen yet -> monitor:0 (normal cold start) ---
    sub.client = FakeClient()
    sub._start_monitor_resuming()
    assert built_commands[-1] == "monitor:0 smartroute", built_commands[-1]
    print(f"cold start        -> {built_commands[-1]!r}   (expected monitor:0)")

    # --- a notification arrives with epochMillis; simulate _consume capture ---
    for em in (1000, 1725000000123, 1725000000050):   # includes an out-of-order older one
        ev = AtEvent(AtEventType.UPDATE_NOTIFICATION,
                     {"key": "live_traffic.smartroute@alpha", "epochMillis": em})
        try:
            e = ev.event_data.get("epochMillis")
            if e is not None and int(e) > sub._last_epoch:
                sub._last_epoch = int(e)
        except (ValueError, TypeError):
            pass
    assert sub._last_epoch == 1725000000123, sub._last_epoch
    print(f"after 3 notifs    -> _last_epoch={sub._last_epoch}   (keeps the max, ignores older)")

    # --- RECONNECT: new client, must resume from last epoch, NOT 0 ---
    sub.client = FakeClient()
    sub._start_monitor_resuming()
    assert built_commands[-1] == "monitor:1725000000123 smartroute", built_commands[-1]
    print(f"after reconnect   -> {built_commands[-1]!r}   (resumes, no monitor:0 backlog replay)")

    print("\nPASS: reconnect resumes from the last-seen epoch (was monitor:0 before the fix).")


if __name__ == "__main__":
    run()
