# Using the fix branch before the PRs merge (e.g. Dart→Python shared keys)

To read Dart-written shared keys in Python **today**, the Python side must run the
`fix/put-get-random-iv` branch (released atsdk decrypts shared values with a fixed zero
IV and can't read Dart's random-IV data).

## Install (verified)

A raw `pip install "git+…@branch"` currently **fails** — not because of the branch, but
a pre-existing repo packaging quirk: `pyproject.toml` points its readme at
`README.PyPI.md`, which is only generated during the CI publish step. So clone and
create it first:

```bash
git clone -b fix/put-get-random-iv https://github.com/atsign-foundation/at_python.git
cd at_python
cp README.md README.PyPI.md          # satisfy pyproject's readme reference (CI-generated normally)
pip install .                        # installs 'atsdk' into your environment
```

Verified: installs into site-packages and includes the branch code
(`at_client.atclient.LEGACY_IV`, `AtClient._iv_from_fetched`).

## Alternative: vendor the changed files
Over an installed released `atsdk` (`pip install atsdk`), overlay from the branch:
- `at_client/atclient.py`
- `at_client/common/metadata.py`
- `at_client/util/verbbuilder.py`

## What works with the branch
- **Dart `put` shared → Python `get` shared** ✅ (Python reads Dart's random IV)
- **Python `put` shared → Dart `get` shared** ✅
- Self keys round-trip in Python with a random IV. Cross-SDK **self** interop is still
  blocked by a separate namespace bug in the Python verb builders (see
  `issues/issue-9-verbbuilder-drops-namespace-self-public.md`) — unrelated to IVs.

## Note
`README.PyPI.md` is CI-generated; don't commit the local copy. Also worth raising
upstream: the repo can't be `pip install`-ed from a git ref as-is because of the missing
readme — the publish workflow should not be the only place that file exists.
