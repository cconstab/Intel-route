# atsdk upstream fixes — status & what to do

We found and fixed several bugs in the Python atSign SDK (`atsdk` / `at_client`,
repo `atsign-foundation/at_python`) while building this migration.

**RESOLVED — v0.2.70 (2026-07-07) shipped the first 5 fixes; v0.2.71 (2026-07-08)
shipped the monitor lifecycle/resume batch** (#529, #530 — verified in the installed
package). Actions taken in this repo:

- ✅ dependency bumped to `"atsdk>=0.2.71"` (README, production guide, deploy/Dockerfile)
- ✅ removed the `AtPublisher.notify` workarounds (manual `iv_nonce` + per-call
  `session_id`) — the SDK does both since 0.2.70
- ✅ **simplified `AtSubscriber` (0.2.71):** the hand-rolled monitor construction is gone —
  reconnects now use `client.start_monitor(regex, last_received_time=_last_epoch)`
  (#530), and `stop()` also calls the connection's `stop_heart_beat()` (#529), so a
  retired subscriber leaves no SDK heartbeat behind. Live-verified on the EE.
- ✅ **kept** what the SDK still doesn't provide: publisher rebuild-and-retry,
  first-contact pre-warm, operator-console watchdog
- 🔬 **asyncio RFC open:** [#531](https://github.com/atsign-foundation/at_python/pull/531)
  — draft `at_client.aio` PoC (async monitor streams; would obsolete the remaining
  hardening if adopted)
- On each running machine: `pip install -U atsdk` in the venv + `git pull`, then
  restart the stack.

## PRs on `atsign-foundation/at_python` — all MERGED

| PR | Branch | Fixes |
|---|---|---|
| [#522](https://github.com/atsign-foundation/at_python/pull/522) | `fix/notify-iv-nonce-and-session-id` | `notify()` auto-generates a **fresh** `iv_nonce` per call; `session_id` fresh per call |
| [#523](https://github.com/atsign-foundation/at_python/pull/523) | `fix/disconnect-resets-connected` | `disconnect()` always clears `_connected` → monitor can rebuild the socket (issue #8) |
| [#524](https://github.com/atsign-foundation/at_python/pull/524) | `fix/shared-key-notification-detection` | monitor `to_string()` called — shared-key notifications were mis-typed (**bug #3**) |
| [#525](https://github.com/atsign-foundation/at_python/pull/525) | `fix/decrypt-error-detail` | shared-key decrypt error interpolates `{e}` (was literal `- e`) |
| [#526](https://github.com/atsign-foundation/at_python/pull/526) | `fix/put-get-random-iv` | random IV for stored keys (put/get), Dart-matched; self+shared; iv_nonce via `UpdateVerbBuilder`; cross-SDK interop test + opt-in CI workflow |

## Issue write-ups filed (no PR yet — need maintainer/design input)

- **first-contact decrypt drop** — new sender's first notification dropped
- **monitor resume on reconnect** — `last_received_time` can't be seeded after client recreate
- **"Failed to decrypt shared_key… Ciphertext length must be equal to key size"** —
  ROOT-CAUSED: **connection desynchronisation, not damaged data.** After a read times
  out the abandoned reply stays queued on the socket, so every later command on that
  connection reads the PREVIOUS command's answer; a shared-key lookup then returns a
  non-ciphertext. The stored record is fine, which is why **restarting clears it**.
  Proved directly: after an abandoned read, `llookup:publickey@bravo` returned the
  earlier `shared_key` reply (`validation/live_desync_test.py`).
  Upstream fix offered in
  [#545](https://github.com/atsign-foundation/at_python/pull/545): `execute_command`
  discards a connection whose reply was never read.
  App side: never reuse a client after a failed send — it is marked stale even when the
  rebuild fails, so a wedged publisher recovers without a restart
  (`validation/live_desync_recovery_test.py`).
  [#544](https://github.com/atsign-foundation/at_python/pull/544) (replace an
  unusable stored key) was **closed as wrong-headed**: the desynchronised case reports
  the identical error, so replacing the key would rotate a perfectly good one. Our
  matching app-side "repair" helper and script were removed for the same reason — the
  damaged-record case was never observed in the wild, only manufactured.
- **verb builders drop the namespace for self/public keys** — cross-SDK naming mismatch
- (Dart-side, separate repo) **`SelfKeyEncryption` zero-IV branch** — dead code / defense-in-depth; real risk is legacy zero-IV self data at rest

---

## When a release > v0.2.69 ships (or you pin trunk) — checklist

1. **Bump the dependency** to the release that contains the fixes in the docs' install
   lines: `README.md` (§Run it), `GETTING_STARTED_PRODUCTION.md` (§1), and `deploy/` if
   pinned. Until then, pin trunk if you need the fixes now (see top).

2. **Optional cleanup** in `smart-route-planning-agent/src/atsign/atsign_io.py` — the
   `AtPublisher.notify` manual `iv_nonce` + per-call `session_id` are now redundant
   (#522 does both in the SDK). They're **harmless to keep** (they just set what the SDK
   would), so this is tidy-up, not required. Re-run the stack end-to-end if you remove
   them, since they touch every publish.

3. **Keep** the app-level resilience regardless — these guard failure modes the SDK does
   NOT yet fix (still issues, not PRs):
   - `AtSubscriber` monitor-resume (`_last_epoch`) and first-contact pre-warm
     (`_ensure_shared_key`);
   - `AtPublisher` rebuild-and-retry on notify failure;
   - **operator console silence-watchdog** (`operator_console.py`) — recreates a wedged
     `atsdk` subscriber; belt-and-suspenders over the SDK monitor even after #523.

4. **Cross-SDK shared keys.** Once #526 is in a release, Dart→Python shared keys work on
   stock `atsdk` — no trunk/branch install needed.

5. **Interop workflow** (`at_python`'s `.github/workflows/interop.yml`) is on trunk now;
   it's `workflow_dispatch` and can be promoted into regular CI/CD (crypto-path PRs or
   nightly).

6. **Local cleanup** (optional): the working clone `/Users/cconstab/scratch/at_python`
   and `dart_client/bin/iv_interop.dart` (its twin ships in the SDK's `test/interop/`).

## Mapping: our workaround → upstream → action

| App workaround | Upstream | Action |
|---|---|---|
| `AtPublisher.notify` sets `iv_nonce` | #522 (merged) | optional remove; harmless to keep |
| `AtPublisher.notify` per-call `session_id` | #522 (merged) | optional remove; harmless to keep |
| `AtSubscriber` monitor-resume (`_last_epoch`) | issue (no PR) | **keep** |
| `AtSubscriber` first-contact `_ensure_shared_key` | issue (no PR) | **keep** |
| `AtPublisher` rebuild + retry | issue (no PR) | **keep** |
| operator console silence-watchdog | app-level (over SDK monitor) | **keep** |

> Track releases at https://github.com/atsign-foundation/at_python/releases. Update this
> file when a version > v0.2.69 ships.
