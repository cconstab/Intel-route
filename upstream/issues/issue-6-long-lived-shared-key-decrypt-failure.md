# Long-lived client fails to decrypt its own shared key after extended operation

**Component:** `at_client` (atsdk)
**Affected versions:** 0.2.69 (PyPI), 0.2.70 (repo `trunk`)
**Severity:** reliability — investigation (root cause not yet isolated)

## Summary
A long-lived client that keeps publishing (encrypt-on-`notify`) can, after a while of
continuous operation, start failing to decrypt the shared key it uses to encrypt to a
peer, and it does not self-recover — every subsequent `notify()` fails until the
process is restarted.

## Symptom
```
Failed to decrypt shared_key.<other>@<me> - <exception>
```
Raised from `get_encryption_key_shared_by_me()` in `at_client/atclient.py` (~L146-148),
which fetches the self-stored shared key (`shared_key.<other>@<me>`) and RSA-decrypts
it with the client's own private key before encrypting the outgoing notification.

> Note: until the accompanying fix (`fix/decrypt-error-detail`) this message printed a
> literal `- e` instead of the interpolated exception, which is why it was previously
> undiagnosable. **With that fix merged, the next occurrence will include the real
> exception** — please attach it here when reproduced.

## What we know
- Occurs only after **extended** operation (not at startup); a fresh client works.
- The self-stored shared key and the client's private key are unchanged, so the most
  likely suspects are connection/key-cache state on the long-lived
  `AtSecondaryConnection`, or the value returned by the `llookup` under a degraded
  connection.
- Not yet isolated to a specific cause — filing as an investigation.

## Reproduction (partial)
Run a client that publishes on a timer to the same peer for an extended period; after
some time `notify()` begins raising the error above and does not recover on its own.
(Full deterministic repro still needed — the `- e` fix is a prerequisite for capturing
the real exception.)

## Requested next step
Merge `fix/decrypt-error-detail` (issue's sibling PR), then capture the full exception
text on the next occurrence and add it here. That should let us classify whether this
is a stale-connection read, a key-cache eviction, or something else.

## Interim workaround (application-side)
On a `notify()` failure, rebuild the `AtClient` (fresh connection + key cache) and
retry once — this recovers without a process restart.
