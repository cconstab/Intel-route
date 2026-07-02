# Cross-SDK IV interop test

Proves the Python at_python `fix/put-get-random-iv` change is wire-compatible with the
Dart reference `at_client` — i.e. random IVs / `ivNonce` for stored keys interoperate
in both directions.

## Files
- `iv_interop.py` — Python helper (uses the at_python branch): put/get self & shared.
- `../../dart_client/bin/iv_interop.dart` — Dart helper (reference `at_client`): put/get
  self & shared, with sync-wait (Dart is local-first: push after put, pull before get).
- `run_interop.sh` — runner + assertions.

## Prereqs
- Ephemeral environment (EE) running; `@alpha`, `@bravo` onboarded (`.atKeys` in
  `/tmp/eehome/.atsign/keys`).
- `AT_PYTHON` = path to the at_python clone on `fix/put-get-random-iv` (default
  `/Users/cconstab/scratch/at_python`).

## Run
```bash
bash upstream/interop/run_interop.sh
```

## Result (verified)
```
A. Python put-shared -> Dart get-shared (random IV)   PASS
B. Dart   put-shared -> Python get-shared (random IV)  PASS
IV INTEROP PASSED
```
A and B are the random-IV shared-key paths in both directions — the behavior this PR
changes. A proves Dart can read Python's random-IV data; B proves Python can read
Dart's.

## Self keys
Self-key interop is **not** asserted here: it's blocked by a separate, pre-existing bug
where the Python verb builders omit the key namespace for self/public keys (see
`../issues/issue-9-verbbuilder-drops-namespace-self-public.md`). That's a naming
mismatch, not an IV issue — self keys use the legacy zero IV in both SDKs, so this PR
doesn't affect them.
