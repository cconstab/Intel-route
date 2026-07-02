Branch: fix/notify-iv-nonce-and-session-id
Title:  fix: notify() generates iv_nonce and a fresh session_id per call

---

`notify()` had two defects, both in `at_client/atclient.py`:

1. **Crashes without a nonce.** It read `at_key.metadata.iv_nonce` and passed it
   straight to `aes_encrypt_from_base64`; if the caller hadn't set it, AES-CTR raised
   `nonce must be bytes-like`. Callers had to set `metadata.iv_nonce` manually.
2. **Shared session_id.** The signature default `session_id=str(uuid.uuid4())` is
   evaluated once at import, so every `notify()` without an explicit id reused the same
   id for the process lifetime. The atServer dedups by notification id, so duplicate /
   rapid notifications were silently dropped.

**Fix:** generate the nonce inside `notify()` when unset (and store it on the key's
metadata so it travels with the notification for the receiver to decrypt), and default
`session_id` to `None`, minting a fresh UUID per call.

**Tests:** `test/notify_test.py` — network-free:
- `session_id` default is `None` (regression against the import-time UUID)
- `notify()` sets `iv_nonce` when the key has none (mocked network)

Found while building a production integration on atsdk; both were reproducible in
isolation (see repros in the reporting project).
