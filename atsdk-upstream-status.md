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
- ✅ **[#545](https://github.com/atsign-foundation/at_python/pull/545) RELEASED in
  v0.2.72 (2026-07-31)** — `execute_command` discards a connection whose reply was never
  read. Verified in the installed package, not just by version number:
  `"disconnect()" in inspect.getsource(AtConnection.execute_command).split("read_the_response")[-1]`
  → `True`. Pin bumped to `atsdk>=0.2.72`.
  **The local guard stays on purpose** — it wraps `AtConnection.read` itself, so it also
  covers the greeting read inside `connect()`, which 0.2.72 still leaves unguarded (see
  candidate **B** below). Running both is a no-op: disconnecting twice does nothing.
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
| [#545](https://github.com/atsign-foundation/at_python/pull/545) | `fix/discard-connection-on-abandoned-read` | a connection whose reply was never read is discarded, so a queued reply can never be served to a later command (**merged 2026-07-30 — awaiting a release > v0.2.71**) |
| [#526](https://github.com/atsign-foundation/at_python/pull/526) | `fix/put-get-random-iv` | random IV for stored keys (put/get), Dart-matched; self+shared; iv_nonce via `UpdateVerbBuilder`; cross-SDK interop test + opt-in CI workflow |

## Candidate PRs from the July 2026 wedge — HELD until validated in production

Found while diagnosing a planner that stopped publishing and never recovered. All three are
implemented locally in `smart-route-planning-agent/src/atsign/atsign_io.py` and covered by
`validation/test_root_connection_recovery.py`. **Deliberately not opened yet:** they fix a
failure we have reasoned about and reproduced synthetically, but have not yet watched
recover in the field. [#544](https://github.com/atsign-foundation/at_python/pull/544) is the
precedent — opened on a root cause that turned out to be wrong, and closed again.

| | Change | Diff | Notes |
|---|---|---|---|
| **A** | `AtClient.__del__` uses `getattr(self, "secondary_connection", None)` | 2 lines | *(re-confirmed against 0.2.72: still unguarded)* | A build that fails before connecting makes the collector raise `AttributeError`, which reads like a crash in the middle of a recoverable retry. No behaviour change for a healthy client. Needs no soak — held only to land with B. |
| **B** | `connect()` disconnects if the greeting read fails | 5 lines | *(re-confirmed against 0.2.72: still unguarded)* | It sets `_connected = True` *before* reading the greeting, so a failed greeting leaves a dead socket marked live and `find_secondary` (`if not self.is_connected()`) never redials. Same shape as the merged #545, applied to the other read. |
| **C** | `AtConnection.__init__` resolves the address once (`getaddrinfo(...)[0][-1]`) and always uses the first entry | 3 lines, but a **design choice** | Options: resolve inside `connect()`; or use `socket.create_connection`, which resolves *and* tries every address but changes timeout semantics (today's explicit `settimeout(None)` is what defeats a bounded connect); or clear the singleton on failure, as we do locally. Maintainers' call — file as an issue with the evidence rather than a drive-by PR. |

**What counts as validated**, so this does not become an indefinite hold:

1. `validation/live_root_recovery_test.py` — poisons the live root singleton (points it at a
   closed port) and asserts the next client build drops it and redials against a real
   atServer. This is deterministic: run it, do not wait for an outage.
2. A real recurrence in the field showing `dropping the shared root connection and
   redialling` followed by `rebuilt after redialling root`, with the service continuing.
   Absence of the failure is *not* evidence — it is rare and environmental.

(1) is enough to open **A** and **B**. **C** should go up as an issue regardless, since the
fix is theirs to choose.

## Issue write-ups filed (no PR yet — need maintainer/design input)

- **`AtClient` is not thread-safe, and does not say so** — one client owns one TLS socket
  carrying one command stream, so two threads sending concurrently interleave their writes
  and each reads the other's reply. It surfaces as
  `[SSL: WRONG_VERSION_NUMBER] wrong version number` or
  `Read on closed or unwrapped SSL socket`, after which the client stays wedged. This is
  easy to hit without realising: our policy engine publishes from its heartbeat loop and
  from its notification callback, which are different threads by construction. Worth either
  documenting the constraint or serialising inside the client. Our side serialises per
  publisher (`AtPublisher.notify`, `validation/test_publisher_serialisation.py`).
- **a dead root server wedges a process permanently** — `AtRootConnection` is a
  process-wide singleton and `AtConnection.__init__` resolves the address once into
  `_addr_info`, so if the root server a process is pinned to stops answering, every later
  `AtClient(...)` fails in `find_secondary` and no amount of client rebuilding recovers;
  only a restart does. Two small fixes would close it upstream: re-resolve (or drop the
  singleton) when a root connection fails, and guard `AtClient.__del__`, which currently
  raises `AttributeError: 'AtClient' object has no attribute 'secondary_connection'` for
  every failed build because `__init__` never got that far — noise that reads like a crash
  in the middle of a recoverable retry. Our side: `atsign_io._reset_root_connection` and a
  guarded `__del__` (`validation/test_root_connection_recovery.py`).
- **`start_monitor()` defaults to replaying the entire retained backlog** —
  `last_received_time=0` is rendered literally as `monitor:0 <regex>`, so a client that
  just wants to watch for new notifications re-receives everything the server still holds.
  The Dart client streams only new ones. This is a sharp edge rather than a bug, but the
  default is the surprising direction: our policy engine re-applied every historical rule
  change on startup, republishing each to the planner, and the planner re-ingested expired
  live records. A `since_now` default (or at least a documented warning) would help. Our
  side seeds the epoch to "now" minus a small grace (`AtSubscriber`, `replay_backlog=True`
  to opt out).
- **first-contact decrypt drop** — new sender's first notification dropped
- **monitor resume on reconnect** — `last_received_time` can't be seeded after client recreate
- **"Failed to decrypt shared_key… Ciphertext length must be equal to key size"** —
  ROOT-CAUSED: **connection desynchronisation, not damaged data.** After a read times
  out the abandoned reply stays queued on the socket, so every later command on that
  connection reads the PREVIOUS command's answer; a shared-key lookup then returns a
  non-ciphertext. The stored record is fine, which is why **restarting clears it**.
  Proved directly: after an abandoned read, `llookup:publickey@bravo` returned the
  earlier `shared_key` reply (`validation/live_desync_test.py`).
  Upstream fix **merged** in
  [#545](https://github.com/atsign-foundation/at_python/pull/545): `execute_command`
  discards a connection whose reply was never read. Not in a release yet (v0.2.71 predates
  it), so the local guard below stays for now.

  **Still valid, and our local version covers one case #545 does not.** #545 wraps the read
  inside `execute_command`; the local guard wraps `AtConnection.read` itself, so it also
  covers the **greeting read inside `connect()`** — and `connect()` sets `_connected = True`
  *before* reading the greeting. Without a disconnect there, a failed greeting leaves a dead
  socket marked live, and `find_secondary` (`if not self.is_connected(): connect()`) never
  redials it: one of the ways the shared root connection wedges. Keeping the local guard
  after #545 ships is therefore worth more than tidiness. A follow-up upstream would be to
  set `_connected` only after the greeting is read, or disconnect if it fails.
  Pinned by `validation/test_root_connection_recovery.py` (case 6).
  App side, two layers:
  1. **the guard**: `atsign_io` applies #545's behaviour locally at import — a connection
     whose read fails is discarded, so a queued reply can never be served to a later
     command. This closes the dangerous silent case (a lookup returning a *different*
     record's value and succeeding, e.g. another recipient's shared key). Remove it once
     #545 ships; leaving it is harmless, as disconnecting twice is a no-op.
     Tests: `validation/test_abandoned_read_guard.py`,
     `validation/live_desync_guard_test.py`.
  2. never reuse a client after a failed send — it is marked stale even when the rebuild
     fails, so a wedged publisher recovers without a restart
     (`validation/live_desync_recovery_test.py`).
  [#544](https://github.com/atsign-foundation/at_python/pull/544) (replace an
  unusable stored key) was **closed as wrong-headed**: the desynchronised case reports
  the identical error, so replacing the key would rotate a perfectly good one. Our
  matching app-side "repair" helper and script were removed for the same reason — the
  damaged-record case was never observed in the wild, only manufactured.
- **verb builders drop the namespace for self/public keys** — cross-SDK naming mismatch
- (Dart-side, separate repo) **`SelfKeyEncryption` zero-IV branch** — dead code / defense-in-depth; real risk is legacy zero-IV self data at rest

---

## When a release > v0.2.71 ships (or you pin trunk) — checklist

0. ~~Remove the abandoned-read guard once #545 ships~~ — **decided against.** #545 is in
   v0.2.72, but the local guard covers strictly more: it wraps `AtConnection.read`, so it
   also catches the greeting read inside `connect()`, which still marks the connection
   `_connected = True` before reading and never disconnects on failure. Removing the guard
   would reopen that path. Revisit if candidate **B** lands upstream.

### Earlier checklist (v0.2.70 / v0.2.71 — done)

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
| `atsign_io` abandoned-read guard (`_discard_connection_on_abandoned_read`) | #545 (merged, unreleased) | remove once a release > v0.2.71 ships; harmless to keep |
| `AtPublisher.notify` per-publisher send lock | `AtClient` thread-safety (issue, no PR) | **keep** |

> Track releases at https://github.com/atsign-foundation/at_python/releases. Update this
> file when a version > v0.2.69 ships.
