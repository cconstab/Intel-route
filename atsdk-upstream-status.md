# atsdk upstream fixes — status & what to do when merged

We found and fixed several bugs in the Python atSign SDK (`atsdk` / `at_client`,
repo `atsign-foundation/at_python`) while building this migration. As of **2026-07-03**
the PR branches are **pushed and awaiting review — NOT yet merged/released**.

Until they merge + a new `atsdk` ships to PyPI, **leave everything as-is**: this project
runs on released `atsdk` 0.2.69 with the application-side workarounds in
`smart-route-planning-agent/src/atsign/atsign_io.py`, and Dart→Python shared-key interop
requires the fix branch (see below).

## PR branches pushed to `atsign-foundation/at_python`

| Branch | Fixes |
|---|---|
| `fix/notify-iv-nonce-and-session-id` | `notify()` auto-generates `iv_nonce`; `session_id` fresh per call (was a shared import-time UUID) |
| `fix/shared-key-notification-detection` | monitor `to_string` called (shared-key notifications were mis-typed) |
| `fix/decrypt-error-detail` | shared-key decrypt error interpolates `{e}` (was literal `- e`) |
| `fix/disconnect-resets-connected` | `disconnect()` always clears `_connected` → monitor can rebuild the socket |
| `fix/put-get-random-iv` | random IV for stored keys (put/get), Dart-matched; self+shared; iv_nonce carried through `UpdateVerbBuilder`; **guarded cross-SDK interop test** (`test/interop_test.py`) + opt-in CI workflow (validated green) |

## Issue write-ups filed (no PR yet — need maintainer/design input)

- **first-contact decrypt drop** — new sender's first notification dropped
- **monitor resume on reconnect** — `last_received_time` can't be seeded after client recreate
- **long-lived "Failed to decrypt shared_key…"** — no self-recovery (now diagnosable via the `- e` fix)
- **verb builders drop the namespace for self/public keys** — cross-SDK naming mismatch
- (Dart-side, separate repo) **`SelfKeyEncryption` zero-IV branch** — dead code / defense-in-depth; real risk is legacy zero-IV self data at rest

---

## When the PRs merge + a new `atsdk` is released — checklist

1. **Bump the dependency.** Pin `atsdk` to the release that contains the fixes in the
   docs' install lines: `README.md` (§Run it), `GETTING_STARTED_PRODUCTION.md` (§1),
   and `deploy/` if pinned. Remove any "install the fix branch" guidance.

2. **Simplify our workarounds** in
   `smart-route-planning-agent/src/atsign/atsign_io.py` — but ONLY the ones the SDK now
   covers (see mapping). The two safe removals once
   `fix/notify-iv-nonce-and-session-id` ships:
   - drop the manual `sk.metadata.iv_nonce = EncryptionUtil.generate_iv_nonce()` in
     `AtPublisher.notify` (SDK generates it);
   - drop the per-call `session_id=str(uuid.uuid4())` (SDK defaults correctly).
   Re-run the stack end-to-end after removing, since these touch every publish.

3. **Keep** the resilient-subscriber pieces until *their* fixes ship (they're issues,
   not PRs yet): monitor-resume (`_last_epoch`), first-contact pre-warm
   (`_ensure_shared_key`), and `AtPublisher` rebuild-and-retry.

4. **Cross-SDK shared keys on stock SDK.** Once `fix/put-get-random-iv` is released,
   Dart→Python shared keys work with released `atsdk` — no branch install needed. Drop
   the branch-install note if referenced anywhere.

5. **Interop workflow.** Once `.github/workflows/interop.yml` is on the default branch
   it's triggerable via `workflow_dispatch` / can be promoted into regular CI/CD (run on
   crypto-path PRs or nightly).

6. **Local cleanup** (optional): delete the working clone
   `/Users/cconstab/scratch/at_python` and the now-redundant
   `dart_client/bin/iv_interop.dart` (its twin ships in the SDK's `test/interop/`).

## Mapping: our workaround → upstream → action when merged

| App workaround (`atsign_io.py`) | Upstream | Action on release |
|---|---|---|
| `AtPublisher.notify` sets `iv_nonce` | PR `fix/notify-iv-nonce-and-session-id` | remove (SDK does it) |
| `AtPublisher.notify` per-call `session_id` | same PR | remove (SDK does it) |
| `AtSubscriber` monitor resume (`_last_epoch`) | issue (no PR) | keep until fixed+released |
| `AtSubscriber` first-contact `_ensure_shared_key` | issue (no PR) | keep until fixed+released |
| `AtPublisher` rebuild + retry on notify failure | issue (no PR) | keep until fixed+released |

> Track PR status at https://github.com/atsign-foundation/at_python/pulls (branches
> `fix/*` above). Update this file as each merges/releases.
