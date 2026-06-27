# atsdk (at_python) — issues found building a notify/subscribe app

**Package:** `atsdk` 0.2.69 (`at_client`) · **Python** 3.13.5 · **OS** macOS (arm64)
**atServer:** local ephemeral environment (`atsigncompany/ephemeral`, `vip.ve.atsign.zone`)

While building a publish/subscribe application (multiple atSigns exchanging encrypted
JSON via `notify()` / `start_monitor()`), we hit several issues. Each has a minimal
description, the root cause, our workaround, and a suggested fix. They're independent —
feel free to split into separate issues.

---

## 1. `notify()` raises `TypeError: nonce must be bytes-like` unless `metadata.iv_nonce` is set

**Repro**
```python
from at_client import AtClient
from at_client.common import AtSign
from at_client.common.keys import SharedKey
c = AtClient(AtSign("@alice"))                       # onboarded
sk = SharedKey("test", AtSign("@alice"), AtSign("@bob")); sk.set_namespace("demo")
c.notify(sk, "hello")                                # boom
```
**Actual:** `TypeError: nonce must be bytes-like` (via `EncryptionUtil.aes_encrypt_from_base64`
→ `modes.CTR(iv)` with `iv=None`).

**Root cause:** `AtClient.notify()` does `iv = at_key.metadata.iv_nonce` (which is `None`
by default) and then calls `EncryptionUtil.aes_encrypt_from_base64(value, shared_key, iv)`.
Passing `iv=None` overrides that function's `iv=b"\x00"*16` default, so AES-CTR gets `None`.

**Workaround:** set `sk.metadata.iv_nonce = EncryptionUtil.generate_iv_nonce()` before every `notify()`.

**Suggested fix:** generate an IV in `notify()` when none is supplied (and keep storing it in
metadata as `ivNonce`, which the receive side already reads):
```python
iv = at_key.metadata.iv_nonce or EncryptionUtil.generate_iv_nonce()
at_key.metadata.iv_nonce = iv
```

---

## 2. `notify()` default `session_id` is evaluated once at import → notifications get de-duplicated

**Symptom:** calling `notify()` repeatedly on the same key with different values (without
passing `session_id`) results in the receiver only ever seeing the **first** value repeated.

**Root cause:** the default argument is evaluated at function-definition (import) time:
```python
def notify(self, at_key, value, operation=OperationEnum.UPDATE, session_id=str(uuid.uuid4())):
```
So every call without an explicit `session_id` reuses the **same** id, and the server
de-duplicates them.

**Workaround:** pass a fresh id each call: `c.notify(sk, value, session_id=str(uuid.uuid4()))`.

**Suggested fix:** use a sentinel default and generate inside the method:
```python
def notify(self, at_key, value, operation=OperationEnum.UPDATE, session_id=None):
    session_id = session_id or str(uuid.uuid4())
```

---

## 3. Monitor does not auto-recover — heartbeat loss → `Bad file descriptor`, then silently stops

**Symptom:** a long-running subscriber (`start_monitor`) stops receiving notifications after a
while. Log:
```
Monitor heartbeats not being received
Wait 5 seconds for monitor to stop
Monitor started on @x
Traceback (most recent call last):
  File ".../at_client/connections/atmonitorconnection.py", line 132, in _run
OSError: [Errno 9] Bad file descriptor
```
After this the monitor thread is dead and no further notifications arrive; `start_monitor`
does not recover on its own.

**Workaround:** wrap `start_monitor` in a loop that recreates the `AtClient` and restarts the
monitor on exit/exception.

**Suggested fix:** auto-reconnect the monitor (recreate the socket and re-issue `monitor`) on
heartbeat loss / socket error, as the Dart SDK does.

---

## 4. Namespaced notification key is delivered without the `.` before the namespace

A `SharedKey(name="live_traffic")` with `set_namespace("smartroute")` is delivered to the
receiver with key `@to:live_trafficsmartroute@from` — i.e. **`live_trafficsmartroute`**, the
dot between key name and namespace is missing. The Dart `at_client` renders the same key as
`live_traffic.smartroute`.

**Impact:** receiver `subscribe`/monitor regexes like `live_traffic.smartroute` don't match,
and cross-SDK (Dart ⇄ Python) key handling diverges. We had to subscribe on the bare
namespace and strip the namespace suffix to recover the key name.

**Suggested fix:** render the fully-qualified key with the `.<namespace>` separator in the
notify path, consistent with `SharedKey.__str__` and the Dart SDK.

---

## 5. `AtRootConnection` race + noisy `__del__` when constructing two AtClients quickly

**Symptom:** constructing a second `AtClient` shortly after the first (e.g. a subscriber +
a publisher for the same atSign) intermittently raises:
```
AttributeError: 'AtRootConnection' object has no attribute '_connected'
```
from `AtConnection.is_connected()` (reads `self._connected` before `__init__` sets it).
The partially-constructed client then triggers:
```
Exception ignored in: <function AtClient.__del__>
AttributeError: 'AtClient' object has no attribute 'secondary_connection'
```

**Workaround:** stagger `AtClient` creation (small delay between clients).

**Suggested fix:** initialize `_connected = False` in `AtRootConnection.__init__` before any
use, make `get_instance` thread-safe, and guard `AtClient.__del__` with `getattr(...)`.

---

Happy to provide full logs or PRs for the small ones (#1, #2, #5) if useful. Thanks for atsdk!
