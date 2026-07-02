Branch: fix/disconnect-resets-connected
Title:  fix: disconnect() always clears _connected even if socket close fails

---

In `at_client/connections/atconnection.py`:

```python
def disconnect(self):
    self._secure_root_socket.close()   # raises on an already-broken socket
    self._connected = False            # skipped when close() raises
```

When the socket is already broken (e.g. `Bad file descriptor`), `close()` itself
raises, so `_connected` is never reset. The monitor restart path is guarded by
`if not self._connected: self._connect()`, so with `_connected` stuck at `True` it
never rebuilds the socket and keeps reading the dead descriptor — the client silently
stops receiving notifications until the whole `AtClient` is recreated.

**Fix:** wrap `close()` and always clear `_connected` in a `finally`.

**Tests:** `test/disconnect_test.py` — network-free; asserts `_connected` becomes
`False` both on a clean close and when `close()` raises `OSError(Bad file descriptor)`.

This is the primary fix for the "monitor never recovers after a drop" behaviour;
see the related issue for the contributing factors (process-global monitor locks and a
non-daemon heartbeat thread that never exits).
