# Monitor cannot resume from last notification after the client is recreated

**Component:** `at_client` (atsdk) — `AtMonitorConnection`
**Affected versions:** 0.2.69 (PyPI), 0.2.70 (repo `trunk`)
**Severity:** reliability / enhancement — missed or duplicated notifications on reconnect

## Summary
When an application recreates its `AtClient` / `AtMonitorConnection` after a monitor
drops (a common resilience pattern, since the monitor can die with
`Bad file descriptor` and not always self-recover), there is **no way to resume the
monitor from the last notification seen**. The fresh connection issues `monitor:0`,
which replays the entire retained backlog (re-delivering stale records) or, depending
on server retention, misses notifications that arrived during the gap.

## Root cause
`at_client/connections/atmonitorconnection.py`:

```python
class AtMonitorConnection(AtSecondaryConnection):
    last_received_time: int = 0      # L18 — CLASS attribute, defaults to 0
    ...
    def _run(self):
        monitor_cmd = "monitor:" + str(self.last_received_time) + " " + self.regex   # L121
```

- `last_received_time` is a **class attribute** with no constructor parameter or
  setter, so a freshly constructed connection always starts at `0`.
- The protocol supports `monitor:<epochMillis>` for incremental resume, and the code
  already updates `last_received_time` from each notification's `epochMillis`
  (~L160-163) — but that state is lost when the connection object is replaced.

Note: the SDK's own heartbeat-driven restart resumes correctly because it reuses the
*same* connection instance. The gap is specifically the recreate-the-client path.

## Symptom
After a reconnect performed by recreating the client:
- **stale replay** — recently-retained notifications are re-delivered (e.g. an old
  incident reappears), or
- **gap** — a notification that arrived during the disconnect window is never
  delivered (depending on the server's notification retention for `monitor:0`).

## Reproduction
1. Subscribe on `@receiver`; process a few notifications (advancing the last-seen
   epoch).
2. Force the monitor to drop and rebuild the `AtClient` (as a resilience loop would).
3. During the down window, send a notification from `@sender`.
4. On reconnect the new monitor issues `monitor:0`; observe backlog replay and/or the
   gap notification's handling.

## Proposed fix
Make `last_received_time` an **instance** attribute with an optional constructor
parameter (and/or a setter), so a caller rebuilding the connection can resume:

```python
def __init__(self, ..., last_received_time: int = 0):
    self.last_received_time = last_received_time
```

Then a reconnect can issue `monitor:<last_epoch>` — each missed notification replayed
exactly once, no full-backlog storm.

## Interim workaround (application-side)
Track the maximum `epochMillis` processed and seed a freshly built
`AtMonitorConnection.last_received_time` before calling `start_monitor()`, so the
reconnect resumes from the last-seen notification.
