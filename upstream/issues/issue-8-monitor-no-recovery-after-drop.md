# Monitor never recovers after a dropped connection — notifications stop until AtClient is recreated

**Component:** `at_client` (atsdk) — `AtConnection` / `AtMonitorConnection`
**Affected versions:** 0.2.69 (PyPI), 0.2.70 (repo `trunk`)
**Severity:** reliability — long-running subscribers silently stop receiving

## Summary
After the monitor connection drops (lost heartbeats or a socket error such as
`Bad file descriptor`), the SDK's self-recovery does not reliably re-establish the
socket. The monitor keeps "restarting" but never rebuilds the connection, so the
client stops receiving notifications until the whole `AtClient` is recreated.

## Primary root cause — `disconnect()` leaves `_connected = True` on a failed close
`at_client/connections/atconnection.py` (~L97):

```python
def disconnect(self):
    self._secure_root_socket.close()   # can raise on a dead/bad fd
    self._connected = False            # skipped when close() raises
```

When the underlying socket is already broken, `close()` itself throws, so
`_connected` is never set to `False`. The monitor restart path then does:

```python
# atmonitorconnection.py start_monitor()
if not self._connected:
    self._connect()     # rebuild socket — but _connected is still True, so this is skipped
self._run()             # reads from the dead socket -> "Bad file descriptor" again -> loop
```

Because `_connected` is still `True`, `connect()`/`_connect()` (which is guarded by
`if not self._connected:`) never rebuilds the socket, and `_run()` keeps failing on
the stale descriptor indefinitely.

## Contributing factors
1. **Process-global locks.** `should_be_running_lock` and `running_lock` are defined
   once in `at_client/util/atconstants.py` and shared by *every* `AtMonitorConnection`
   instance, while `running`/`should_be_running` are per-instance. A recreated monitor
   (or a second atSign in the same process) contends on the same global locks.
2. **Heartbeat thread never exits.** `start_heart_beat()` spawns a **non-daemon**
   thread running `while True:` with no termination condition. When an app abandons a
   monitor (e.g. recreates the `AtClient` to recover), the old heartbeat thread keeps
   running forever — leaking threads and continuing to contend the global locks and
   toggle shared state.

## Symptom
```
Monitor heartbeats not being received
... Bad file descriptor
Monitor restart failed ...
```
repeating, with no notifications delivered thereafter.

## Reproduction
1. Subscribe on an atSign (monitor running).
2. Interrupt connectivity long enough to break the socket (or force-close it).
3. Observe the monitor attempts to restart but never rebuilds the connection; no
   further notifications arrive until the `AtClient` is recreated.

Observed repeatedly in a long-running subscriber during a migration project.

## Proposed fixes
- **`disconnect()` must always reset state** (primary fix, small):
  ```python
  def disconnect(self):
      try:
          self._secure_root_socket.close()
      except Exception:
          pass
      finally:
          self._connected = False
  ```
  (See PR `fix/disconnect-resets-connected`.)
- Make the heartbeat thread a **daemon** with a clean exit when the connection is
  stopped/abandoned, so recreated clients don't leak zombie threads.
- Scope the monitor locks to the instance (or otherwise avoid one global pair shared
  across all connections).

## Interim workaround (application-side)
Wrap the subscriber so it recreates the `AtClient` and restarts the monitor on death.
This works but leaks the old heartbeat thread and still contends the global locks —
so it's a mitigation, not a cure.
