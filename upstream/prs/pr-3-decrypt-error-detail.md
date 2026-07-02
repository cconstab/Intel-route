Branch: fix/decrypt-error-detail
Title:  fix: include exception detail in shared-key decrypt error

---

In `at_client/atclient.py`, `get_encryption_key_shared_by_me()` raised:

```python
raise AtDecryptionException(f"Failed to decrypt {to_lookup} - e")
```

The `e` is a literal character, not the interpolated exception, so shared-key decrypt
failures printed `... - e` with no detail — making the underlying problem impossible
to diagnose. The sibling handlers (same file, ~L169 and ~L310) correctly use `{e}`.

**Fix:** interpolate the exception (`- {e}`).

**Tests:** `test/decrypt_error_test.py` — network-free; forces a decrypt failure via a
mocked connection and asserts the raised message includes the real exception (not the
literal `e`).

Small, isolated, and unblocks diagnosis of an intermittent "Failed to decrypt
shared_key…" seen on long-lived clients.
