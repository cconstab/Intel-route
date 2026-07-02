Branch: fix/shared-key-notification-detection
Title:  fix: detect shared-key notifications (call to_string())

---

In `at_client/connections/atmonitorconnection.py` the monitor classified incoming
notifications with:

```python
if key.startswith(str(self.atsign.to_string) + ":shared_key@"):
```

`self.atsign.to_string` is a **bound method**, so `str(...)` of it is a method repr
(e.g. `<bound method AtSign.to_string of ...>`) that never prefixes a real key. As a
result `SHARED_KEY_NOTIFICATION` was never emitted and shared-key notifications were
mis-typed as ordinary `UPDATE_NOTIFICATION`s. (Line 124 in the same file correctly
uses `to_string()`, so this is an isolated missing-parentheses bug.)

Consequence: the client never caches incoming shared keys via the notification path
and always falls back to lookup-on-demand — which contributes to first-contact decrypt
failures.

**Fix:** extract the check into a testable static helper
`_is_shared_key_notification(atsign, key)` that calls `to_string()`.

**Tests:** `test/monitor_shared_key_test.py` — network-free, both branches
(shared-key key vs. regular update key).
