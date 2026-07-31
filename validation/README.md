# Validation: Python `atsdk` notify → monitor round-trip + Python⇄Dart interop (Path B go/no-go)

*This is the de-risking spike that proved Path B before the build — kept as the validation record.*

**Goal:** de-risk Path B by proving the Beta Python SDK (`atsdk` / `at_python`) can
**publish** (`notify`) and **subscribe** (`start_monitor`) a `LiveTrafficData`
payload between two atSigns — the mechanism the native migration depends on.

**Verdict: GO — fully validated end-to-end, including cross-language.** A live
`notify → monitor` round-trip between two atSigns (`@alpha → @bravo`) on a local
ephemeral atServer delivered, decrypted, and validated distinct `LiveTrafficData`
payloads (densities 3/6/9/14, incident flips to `crowding` at 14). Two Beta-SDK
rough edges were found and fixed in `publisher.py` (see "Beta-SDK gotchas").

**Cross-language interop (Python `atsdk` ⇄ Dart `at_client`): GREEN — no blockers.**
The planner is Python and the commuter app is Dart/Flutter, so this was the last real
unknown. Both directions verified against the live atServer:
- **Python `@alpha` → Dart `@bravo`** (planner → commuter): Dart decrypted the JSON
  intact (densities 3, 6) — zero decrypt errors.
- **Dart `@bravo` → Python `@alpha`** (commuter → planner): `status=delivered`; Python
  decrypted + validated it (`density=17, incident=crowding`).
The encrypted-JSON wire under shared keys is fully interoperable between the two SDKs.
Dart code in [`../dart_client/`](../dart_client/).

---

## Offline regression tests

Network-free, so they run anywhere and gate a change without an atServer. Each one pins a
failure that actually happened:

| Test | What it pins |
|------|--------------|
| `test_publisher_serialisation.py` | One publisher never runs two sends at once. A shared publisher used from two threads interleaved writes on its single TLS socket (`[SSL: WRONG_VERSION_NUMBER]`, `Read on closed or unwrapped SSL socket`) and wedged, silently stranding the planner on an old rule set. Removing the lock makes this test report overlapping sends. |
| `test_policy_persistence.py` | A revocation survives a restart: the engine reads back its own rule records, `--grant` seeds only a store that has never been written, an empty set means "everything revoked", an unreadable store raises rather than re-authorising everyone, and a rule another atSign *shares* with the engine is never read back as a grant. Its fake secondary validates the scan command against the SDK's own `ScanVerbBuilder` — an earlier version accepted a hand-built `scan:rule.`, which a real server rejects with `AT0003`, so the suite passed green while the engine could not start. |
| `test_root_connection_recovery.py` | A dead root server cannot wedge the process. The SDK's root connection is a singleton that resolves its address once, so every client build kept failing in `find_secondary` (seen as `EOF occurred in violation of protocol` plus an `AttributeError` from `__del__`) with no recovery until restart. A failed build now drops it and redials, under a lock so two threads cannot race the singleton. |
| `test_abandoned_read_guard.py` | A connection whose reply was never read is discarded, so a queued reply can never be served to a later command (upstream [#545](https://github.com/atsign-foundation/at_python/pull/545)). |
| `test_subscriber_liveness.py` | Heartbeat acks count as liveness; true silence forces a reconnect. |
| `test_monitor_resume.py` | A cold start streams only new notifications (the SDK sends `monitor:0` verbatim, which replays the whole retained backlog), and a reconnect resumes from the newest epoch processed — no gap, no replay. |
| `test_first_contact_retry.py` | A new sender's first record is not dropped while its shared key propagates. |
| `test_policy_revoke_purge.py` | A revocation purges the publisher's cached data immediately, so no reroute lingers. |
| `test_operator_watchdog.py` | The console self-heals a wedged subscriber. |

Run them all:

```bash
PYTHONPATH=smart-route-planning-agent/src python validation/test_<name>.py
```

The `live_*.py` scripts need a running atServer and are the paired live proofs (frozen-peer
outage, desynchronisation, and recovery). `live_root_recovery_test.py` is the one to reach
for deliberately: it poisons the process-wide root connection so the recovery path can be
proved on demand instead of waiting for a real root-server outage.

## Files

| File | What it is |
|------|-----------|
| `payload.py` | Wire contract — `LiveTrafficData`-shaped dict + encode/decode/validate (mirrors `schema.py`) |
| `publisher.py` | Intersection-style publisher: `AtClient.notify(SharedKey, json)` |
| `subscriber.py` | Planner-style subscriber: `AtClient.start_monitor(regex)` + cache |
| `selftest.py` | Offline checks (no keys/network): API surface, key naming, payload round-trip |
| `../scripts/onboard_ee.py` | CRAM → PKAM onboarding to mint `.atKeys` (moved to scripts/ — used by `onboard_all_ee.py`) |
| `../dart_client/` | Dart `at_client` programs: `change_route.dart` (demo tool) + `dart_publisher`/`dart_subscriber` (interop test) |

## Results

| Check | Result |
|-------|--------|
| `pip install atsdk` (0.2.69) | ✅ |
| Offline self-test (API + key name `live_traffic.smartroute` + payload) | ✅ all pass |
| TLS connect to atServer (client, relaxed verify for local EE) | ✅ |
| CRAM onboard → PKAM auth → key generation/storage | ✅ `@alpha`, `@bravo` |
| Local lookups (`llookup` of own public key) | ✅ |
| `notify()` publishes encrypted payload | ✅ |
| Cross-secondary `plookup` of recipient public key (server→server TLS) | ✅ |
| Encrypted notification delivered, decrypted & validated at subscriber | ✅ distinct 3/6/9/14 |

**Cert gotcha (resolved):** the cached `atsigncompany/ephemeral` image shipped an
**expired** `CN=vip.ve.atsign.zone` cert (`notAfter Nov 13 2025`). The Python client
bypasses verification, but the **Dart secondaries enforce it**, so secondary→root
TLS threw `HandshakeException` and `plookup` failed. **`docker pull` fetched a fresh
image** (cert valid May 15 → Aug 13 2026) → `HandshakeException` count 0 → green.
Lesson: keep the EE image current (or build it fresh).

## Beta-SDK gotchas found & fixed (baked into `publisher.py`)

1. **`notify()` needs an IV.** It reads `at_key.metadata.iv_nonce` and passes it
   straight to AES-CTR; if unset it's `None` → `nonce must be bytes-like`. Fix:
   `sk.metadata.iv_nonce = EncryptionUtil.generate_iv_nonce()` before each notify
   (the IV travels in the notification metadata; the receiver decrypts with it).
2. **`notify()`'s default `session_id` is evaluated once at import** (`= str(uuid.uuid4())`),
   so every notification shares one id and the server **dedups** them (you'd see
   the first value repeated). Fix: pass `session_id=str(uuid.uuid4())` per send.

## Key SDK facts learned (for the real build)

- `AtClient(atsign, root_address=Address.from_string(host:port), queue=Q)` — pass
  `root_address` explicitly; **default is `root.atsign.org` (prod)**.
- Publish: `client.notify(SharedKey(name, frm, to).set_namespace("smartroute"), json)`.
- Subscribe: `client.start_monitor("smartroute")` + a thread draining the `Queue`;
  call `client.handle_event(q, ev)` then read `ev.event_data["decryptedValue"]`
  on `AtEventType.DECRYPTED_UPDATE_NOTIFICATION`. (Same queue+thread pattern Intel's
  `main.py` already uses.)
- Fully-qualified key renders as `@to:live_traffic.smartroute@from` — regex
  `smartroute` matches it for monitoring.
- Keys are read/written at `~/.atsign/keys/<atSign>_key.atKeys` — isolate with a
  custom `HOME` so test keys never collide with real ones.

## How to run (once the EE has a valid cert)

```bash
# 0. isolate keystore + relax client TLS for the local EE only
export HOME=/tmp/eehome
export PYTHONPATH=/tmp/ee_site:$PWD          # /tmp/ee_site/sitecustomize.py relaxes client TLS

# 1. start the ephemeral environment (see note on certs below)
#    vip.ve.atsign.zone is the VIP the cert+EE expect; it must reach the root.
docker run -d --name atsign-ee --add-host vip.ve.atsign.zone:127.0.0.1 \
  -e DNS_FQDN=vip.ve.atsign.zone -e FIRST_PORT=2500 \
  -p 64:64 -p 2500-2540:2500-2540 atsigncompany/ephemeral

# 2. onboard two atSigns with their CRAM secrets (from the container)
ALPHA=$(docker exec atsign-ee cat /atsign/atservers/alpha/CRAM)
BRAVO=$(docker exec atsign-ee cat /atsign/atservers/bravo/CRAM)
python ../scripts/onboard_ee.py -a @alpha -c "$ALPHA" -r vip.ve.atsign.zone:64
python ../scripts/onboard_ee.py -a @bravo -c "$BRAVO" -r vip.ve.atsign.zone:64

# 3. round-trip
python subscriber.py --atsign @bravo --regex smartroute --root vip.ve.atsign.zone:64 &
python publisher.py  --atsign @alpha --to @bravo --namespace smartroute \
  --count 3 --interval 3 --root vip.ve.atsign.zone:64
```

## To get a 100%-green live delivery — fix the EE cert (pick one)

1. **Build the EE image fresh** from `at_server/tools/build_ephemeral_environment`
   so it bakes a current cert (the prebuilt image's cert has expired).
2. **Create the VIP properly** on a host where `vip.ve.atsign.zone → 10.64.64.64`
   and drop in valid certs the Dart secondaries trust.
3. Run on the Atsign virtual-environment host (e.g. `furl-was-01`) where the VIP
   and certs are already correct.

Offline self-test + onboarding/auth already prove the SDK; only the cert-gated
delivery hop remains, and it is environment, not code.
