# First notification from a new sender is silently dropped (shared-key not yet resolved)

**Component:** `at_client` (atsdk)
**Affected versions:** 0.2.69 (PyPI), 0.2.70 (repo `trunk`)
**Severity:** reliability — first record from any new sender can be lost

## Summary
The very first notification received from a sender the client hasn't communicated
with before is silently dropped. In practice you "have to send it twice to wake it
up": the first send is lost, the second (once the shared key has propagated) is
delivered.

## Symptom
On the receiving side, a line like:

```
<ts>: caught exception argument should be a bytes-like object or ASCII string,
not 'NoneType' while decrypting received data with key name
[@receiver:shared_key@sender]
```

…and the notification never reaches the application (`handle_event` re-enqueues a
`DECRYPTED_UPDATE_NOTIFICATION` only on success).

## Root cause
`at_client/atclient.py`, `handle_event()` UPDATE branch (~L404-417):

```python
encryption_key_shared_by_other = self.get_encryption_key_shared_by_other(SharedKey.from_string(key=key))
decrypted_value = EncryptionUtil.aes_decrypt_from_base64(..., self_encryption_key=encryption_key_shared_by_other, ...)
...
except Exception as e:
    print(... "while decrypting received data with key name [" + key + "]")   # swallowed, dropped
```

When the sender's shared key hasn't propagated to the receiver yet,
`get_encryption_key_shared_by_other()` (~L150) can't resolve it, decryption fails,
and the exception is caught, printed, and the notification is **dropped with no
retry and no re-queue**.

Likely aggravated by the shared-key-notification mis-detection bug (see PR
`fix/shared-key-notification-detection`): because `SHARED_KEY_NOTIFICATION` was
never emitted, the client never cached the incoming shared key proactively and
always fell back to the lookup-on-demand path that races here.

## Reproduction
1. Onboard two atSigns that have never communicated (e.g. `@sender`, `@receiver`).
2. Subscribe on `@receiver` (monitor).
3. From `@sender`, send exactly **one** `notify()` to `@receiver`.
4. Observe: the first notification is frequently dropped with the decrypt error
   above; a second identical send succeeds.

Reproduced live against an ephemeral environment during a migration project
(first-contact from a freshly onboarded sender).

## Impact
Any workflow where a record matters on first contact (one-shot commands, the first
reading from a newly joined publisher) can lose that record. Long-running senders
mask it because they retry on a timer.

## Proposed fix
On a decrypt failure caused by an unresolved shared key, either:
- retry `get_encryption_key_shared_by_other()` a few times with a short backoff (the
  key typically propagates within ~1s), or
- re-enqueue the raw event for a later processing attempt.

Composing with the `SHARED_KEY_NOTIFICATION` detection fix (so the key is cached
from the notification path) should reduce how often the lookup path is hit at all.

## Interim workaround (application-side)
Pre-resolve the sender's shared key with a short retry *before* calling
`handle_event`, so the key is cached and the first decrypt succeeds.
