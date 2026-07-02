# atsdk (at_python) — findings for upstream

Bugs found while building the Smart Route Planning migration on the Python atSign
SDK. Verified against **atsdk 0.2.69** (PyPI) and confirmed still present in
**0.2.70** (repo `trunk`). Upstream: https://github.com/atsign-foundation/at_python

Runnable, network-free repros for #1–#3 live in [`repro/`](repro/). #4–#6 were
reproduced live against an ephemeral environment during this project.

Proposed sequencing: land the three **Easy** fixes first (small, obviously correct),
open **issues + design discussion** for #4/#5, and file #6 as an investigation.

---

## 1. `notify()` crashes when `iv_nonce` is unset  — Easy

- **Source:** `at_client/atclient.py`, `notify()` (~L423-429)
- **Symptom:** `notify()` raises `TypeError: nonce must be bytes-like` / `argument
  should be a bytes-like object or ASCII string, not 'NoneType'` unless the caller
  first sets `at_key.metadata.iv_nonce`.
- **Root cause:**
  ```python
  iv = at_key.metadata.iv_nonce                       # None unless caller set it
  encrypted_value = EncryptionUtil.aes_encrypt_from_base64(value, shared_key, iv)
  ```
  AES-CTR needs a nonce; `iv=None` crashes.
- **Repro:** [`repro/repro_notify_iv_nonce.py`](repro/repro_notify_iv_nonce.py)
- **Proposed fix:** generate a nonce inside `notify()` when none is provided, and set
  it on the key's metadata so it travels with the notification:
  ```python
  iv = at_key.metadata.iv_nonce
  if iv is None:
      iv = EncryptionUtil.generate_iv_nonce()
      at_key.metadata.iv_nonce = iv
  ```
- **Test:** integration (config.ini style) round-trip notify→receive→decrypt with an
  AtKey that has no iv_nonce set.

## 2. `session_id` default is evaluated once at import  — Easy

- **Source:** `at_client/atclient.py`, `notify()` signature (~L423)
- **Symptom:** every `notify()` call that doesn't pass `session_id` reuses the SAME id
  for the process lifetime; the atServer dedups by id, so duplicate/rapid
  notifications get silently dropped.
- **Root cause:** classic mutable-default-once pitfall:
  ```python
  def notify(self, at_key, value, operation=OperationEnum.UPDATE, session_id=str(uuid.uuid4())):
  ```
  `str(uuid.uuid4())` runs at function-definition time, not per call.
- **Repro:** [`repro/repro_session_id_default.py`](repro/repro_session_id_default.py)
  (prints the single fixed UUID baked into the default).
- **Proposed fix:**
  ```python
  def notify(self, at_key, value, operation=OperationEnum.UPDATE, session_id=None):
      if session_id is None:
          session_id = str(uuid.uuid4())
  ```
- **Test:** network-free — assert `inspect.signature(AtClient.notify)
  .parameters['session_id'].default is None`.

## 3. Shared-key notifications never detected (missing `()`)  — Easy

- **Source:** `at_client/connections/atmonitorconnection.py` (~L167)
- **Symptom:** `SHARED_KEY_NOTIFICATION` is never emitted; shared-key notifications are
  mis-typed as ordinary `UPDATE_NOTIFICATION`s. This means the client never caches an
  incoming shared key via the notification path and always falls back to the
  lookup-on-demand path — which contributes to #4 (first-contact decrypt failures).
- **Root cause:** `to_string` is called without parentheses (line 124 in the same file
  correctly uses `to_string()`):
  ```python
  if key.startswith(str(self.atsign.to_string) + ":shared_key@"):   # bound method, never matches
  ```
- **Repro:** [`repro/repro_shared_key_notification_detection.py`](repro/repro_shared_key_notification_detection.py)
- **Proposed fix:**
  ```python
  if key.startswith(self.atsign.to_string() + ":shared_key@"):
  ```
- **Test:** extract the predicate into a small static helper
  (`_is_shared_key_notification(atsign_str, key)`) and unit-test both branches
  (network-free).

## 4. First-contact notification dropped on decrypt  — Medium (design)

- **Source:** `at_client/atclient.py`, `handle_event()` UPDATE branch (~L404-417),
  `get_encryption_key_shared_by_other()` (~L150)
- **Symptom:** the first notification from a never-seen sender is silently lost:
  `caught exception ... while decrypting received data with key name
  [@me:shared_key@sender]`. Practically: "you have to send it twice to wake it up."
- **Root cause:** when the sender's shared key hasn't propagated yet,
  `get_encryption_key_shared_by_other` raises; `handle_event` catches, prints, and
  drops the notification — no retry, no re-queue.
- **Repro (live):** fresh sender → subscriber, single notify; first record is dropped
  under load. Reproduced live in this project (EE, `@charlie` first-contact).
- **Proposed fix (needs maintainer input):** on decrypt failure due to a missing
  shared key, retry `get_encryption_key_shared_by_other` briefly (the key propagates
  within ~1s), or re-enqueue the event for a later attempt. Likely composes with #3
  (once shared-key notifications are detected, the key is cached proactively).
- **Interim workaround (ours):** pre-resolve the sender's shared key with retry before
  handling the event (application-side wrapper).

## 5. Monitor can't resume after client recreation  — Medium (enhancement)

- **Source:** `at_client/connections/atmonitorconnection.py` (L18 class attr, L121 cmd)
- **Symptom:** a caller that recreates `AtClient`/`AtMonitorConnection` after a monitor
  death cannot resume from the last-seen notification: `last_received_time` is a
  **class attribute** defaulting to `0`, with no constructor param or setter, so the
  new monitor issues `monitor:0` and replays the entire retained backlog (or, per
  server retention, risks a gap).
- **Root cause:** no API to seed the resume position on a fresh connection.
- **Proposed fix:** make `last_received_time` an instance attribute with an optional
  constructor parameter (and/or a setter), so callers can resume with
  `monitor:<last_epoch>`. The SDK's own heartbeat-driven restart already resumes on the
  *same* instance; this only closes the recreate-the-client gap.
- **Interim workaround (ours):** track the max `epochMillis` seen and seed a freshly
  built monitor connection before `start_monitor`.

## 6. Long-lived client: "Failed to decrypt shared_key…" after a while  — Investigate

- **Symptom:** after extended operation, an encrypt-on-notify path fails with
  `Failed to decrypt shared_key.<other>@<me> - e`; the client does not self-recover.
- **Status:** root cause not yet isolated (suspected connection/key-cache state). The
  real exception was **hidden by #7** (`- e` literal) — with #7 fixed, the next
  occurrence prints the actual error, which should let us classify this. File as an
  investigation issue rather than a PR. Interim workaround (ours): rebuild the client
  and retry once on notify failure.

## 7. Shared-key decrypt error hides the real exception  — Easy (done)

- **Source:** `at_client/atclient.py`, `get_encryption_key_shared_by_me()` (~L148)
- **Symptom:** decrypt failures raise `Failed to decrypt <key> - e` — a literal `e`,
  not the exception. This is what made #6 undiagnosable.
- **Root cause:** f-string typo — `- e` instead of `- {e}` (sibling handlers at L169
  and L310 correctly use `{e}`).
- **Fix:** interpolate `{e}`. Branch `fix/decrypt-error-detail` (with a mocked,
  network-free test).

> Note: line 157's `str(shared_key.shared_by)` was initially suspected but is **fine** —
> `AtSign.__str__` is defined and equals `to_string()`.

---

### Notes on contributing
- Fork-based workflow; conventional-commit / semantic-PR titles (see repo
  `CONTRIBUTING.md`).
- Existing tests are integration-style (`config.ini` atSigns) and skip for dependabot
  PRs (`@skip_if_dependabot_pr`); add network-free unit tests where possible (#2, #3)
  and integration tests for the rest.
