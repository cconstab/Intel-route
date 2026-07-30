#!/usr/bin/env python3
"""
Network-free tests for the subscriber's liveness watchdog and bounded reads.

The SDK connects with settimeout(None) and reads a byte at a time, so a peer that
goes silent without closing the connection (network change, NAT timeout, sleep,
frozen server) never raises — the reconnect loop would wait forever. The watchdog
force-closes the connection so that loop can run.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

import atsign.atsign_io as aio  # noqa: E402


class FakeSocket:
    def __init__(self):
        self.timeout = None

    def settimeout(self, seconds):
        self.timeout = seconds


class FakeMonitorConnection:
    def __init__(self):
        self.heart_stopped = False
        self.disconnected = False

    def stop_heart_beat(self):
        self.heart_stopped = True

    def disconnect(self):
        self.disconnected = True


class FakeClient:
    def __init__(self):
        self.monitor_connection = FakeMonitorConnection()
        self.secondary_connection = type("C", (), {"_secure_root_socket": FakeSocket()})()


def main():
    # --- bounded reads: the command socket must get a finite timeout ---
    client = FakeClient()
    aio._bound_socket_reads(client, 30.0)
    assert client.secondary_connection._secure_root_socket.timeout == 30.0
    print("bounded reads    -> command socket timeout set (was None = forever)")

    # tolerates a client that doesn't expose the private attribute
    aio._bound_socket_reads(object(), 30.0)
    print("bounded reads    -> no crash when the attribute is absent")

    sub = aio.AtSubscriber("@alpha", "smartroute", on_record=lambda *a: None,
                           silence_timeout_s=5.0)
    sub.client = FakeClient()

    # --- recent activity: must NOT intervene ---
    sub._last_event_at = time.monotonic()
    assert sub._watchdog_tick() is False
    assert sub.client.monitor_connection.disconnected is False
    print("recent activity  -> watchdog leaves the connection alone")

    # --- silence: must force-close so the blocked read errors and start() reconnects ---
    sub._last_event_at = time.monotonic() - 60
    assert sub._watchdog_tick() is True
    assert sub.client.monitor_connection.heart_stopped is True
    assert sub.client.monitor_connection.disconnected is True
    print("silence          -> heartbeat stopped and monitor socket closed")

    # --- and it grants a grace period rather than firing every tick ---
    assert sub._watchdog_tick() is False
    print("after firing     -> grace period before the next intervention")

    # --- any event counts as liveness, including a heartbeat ack (no publishers needed) ---
    sub._last_event_at = time.monotonic() - 60
    sub._running = True
    from at_client.connections.notification.atevents import AtEvent, AtEventType
    sub.q.put(AtEvent(AtEventType.MONITOR_HEARTBEAT_ACK, {"key": "__heartbeat__"}))
    import threading
    threading.Thread(target=sub._consume, daemon=True).start()
    time.sleep(1.5)
    sub._running = False
    assert time.monotonic() - sub._last_event_at < 5, "heartbeat ack did not refresh liveness"
    assert sub._watchdog_tick() is False
    print("heartbeat ack    -> refreshes liveness (a quiet namespace is not a dead one)")

    print("\nPASS: silent-death is detected and forced to reconnect; quiet is not silent.")


if __name__ == "__main__":
    main()
