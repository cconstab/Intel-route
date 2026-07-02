# Verb builders drop the key namespace for self/public keys (breaks cross-SDK naming)

**Component:** `at_client` (atsdk) — `util/verbbuilder.py`
**Affected versions:** 0.2.69 (PyPI), 0.2.70 (repo `trunk`)
**Severity:** interop / correctness

## Summary
`LlookupVerbBuilder.with_at_key()` (and the other lookup/update builders) set the key
name with `at_key.name` — the **bare** key without its namespace — and never append the
namespace. So a self/public key lookup is built as `llookup:all:foo@alice` instead of
`llookup:all:foo.itest@alice`. `str(at_key)` correctly includes the namespace, so the
builder disagrees with the key's own string form.

## Impact
- **Cross-SDK naming mismatch:** the Dart `at_client` stores/reads self keys as
  `foo.itest@alice`; Python stores/reads `foo@alice`. So a self (or public) key written
  by one SDK is invisible to the other — not a crypto problem, a naming one.
- Python↔Python happens to work only because put and get are *consistently* wrong (both
  omit the namespace).

## Root cause
`at_client/util/verbbuilder.py`, `LlookupVerbBuilder.with_at_key`:
```python
def with_at_key(self, at_key, type):
    self.set_key_name(at_key.name)     # <-- bare name, no namespace
    self.set_shared_by(str(at_key.shared_by))
    ...
```
`build()` then emits `... + self.key + format_atsign(self.shared_by)` with no namespace.
(Shared-key gets that use `str(shared_key)` are unaffected — `str` includes the
namespace.)

## Reproduction
```python
from at_client.common import AtSign
from at_client.common.keys import SelfKey
from at_client.util.verbbuilder import LlookupVerbBuilder
k = SelfKey('foo', AtSign('@alice')); k.set_namespace('itest')
print(str(k))                                                   # foo.itest@alice
print(LlookupVerbBuilder().with_at_key(k, LlookupVerbBuilder.Type.ALL).build())
# -> llookup:all:foo@alice   (namespace dropped)
```
Also observed live: a Dart-written self key `foo.itest@alice` is reported
`key not found` by Python (it looks up `foo@alice`), and vice-versa.

## Proposed fix
Include the namespace in the builder's key (mirroring `str(at_key)` / the Dart SDK),
e.g. use `at_key.name + ('.' + namespace if namespace else '')` (respecting
`is_public`/`is_hidden`/`shared_with` ordering). Applies to `LlookupVerbBuilder`,
`LookupVerbBuilder`, `PlookupVerbBuilder`, and `UpdateVerbBuilder`.

**Backward-compat caution:** existing Python-written self/public keys are stored
namespace-less; a straight fix could make them unreadable. Consider a migration or a
fallback lookup (try with namespace, then without) — worth maintainer input.

## Found via
Cross-SDK IV interop testing (Python at_python `fix/put-get-random-iv` ⇄ Dart
`at_client`): shared-key interop passed both directions; self-key interop failed on
this naming mismatch, not on encryption.
