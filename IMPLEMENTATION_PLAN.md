# Implementation Plan — Smart Route Planning on the Atsign Platform (Path B)

**Source of truth:** [blueprints/path-b-native-atsign.blueprint.json](blueprints/path-b-native-atsign.blueprint.json)
(14 nodes / 16 edges, validated). Companion docs: [PRD.md](PRD.md) ·
[atsign-migration-assessment.md](atsign-migration-assessment.md) ·
[path-comparison-and-recommendation.md](path-comparison-and-recommendation.md) ·
validation/spike: [validation/README.md](validation/README.md).

Scope: build **Path B** (native pub/sub). Path A (NoPorts drop-in) remains the
fallback / "act 1" of the demo.

---

## 1. Node → component → Atsign map (from the blueprint)

| Blueprint node | Build as | Atsign | Reuse status |
|----------------|----------|--------|--------------|
| Smart Route Planner | Python service: LangGraph + atsdk subscriber/publisher (headless) | `@smartroute_planner` | KEEP brain; SWAP `live_traffic.py`; ADD comms |
| Intersection Agent — Market St / 5th Ave / Broadway | Python publisher (CSV-driven for demo) | `@intxn_market_st`, `@intxn_5th_ave`, `@intxn_broadway` | ADD (not in repo) |
| Weather Feed | Python publisher wrapping `weather_report.py` | `@weather_feed` | reuse controller |
| Traffic Trends Feed | Python publisher wrapping `traffic_trends.py` | `@traffic_trends_feed` | reuse controller |
| Planned Events Feed | Python publisher wrapping `planned_events.py` | `@events_feed` | reuse controller |
| Operator Console (Gradio) | Python Gradio app (reused `main.py`) + atsdk subscriber | `@route_operator` | KEEP UI |
| Commuter Mobile App | Flutter app (`at_client_flutter`) | `@commuter01` (per commuter) | ADD (new) |
| Policy Manager | Python authorization service (the policy plane) | `@route_policy` | ADD (new) |
| Policy Admin (person) | Security/ops owner of the access rules | `@route_policy_admin` | — |
| Roadside Cameras & Sensors | Demo: CSV replay (no real cameras) | — | — |
| Route & Map Data | GPX files held by planner | — (under `@smartroute_planner`) | KEEP |
| Map Tile Service | External OSM tiles (HTTP) | — (external) | KEEP |
| Commuter / Operator (people) | The humans | their own Atsign | — |

**Namespace:** `smartroute` → keys render as `<name>.smartroute@<atsign>`.

---

## 2. Tech-stack decisions (locked)

- **Planner + all publishers + operator console → Python**, using **`atsdk`**
  (`at_python`, validated in the spike). Keeps Intel's LangGraph/GPX/Gradio code reused.
- **Commuter app → Flutter/Dart**, using **`at_client_flutter`** (the canonical,
  supported mobile SDK; the Atsign implementation rules' Flutter requirements apply).
- **Wire = encrypted JSON** under shared keys; Python and Dart both speak atProtocol,
  so they interoperate — **must be verified once** (see Phase 1 interop spike).
- **Communication pattern:** event-driven notifications
  (`notify` / `subscribe` ≈ Python `notify` / `start_monitor`).

### Spike learnings already baked in (see `validation/publisher.py`)
1. `notify()` needs `sk.metadata.iv_nonce = EncryptionUtil.generate_iv_nonce()` per send.
2. `notify()`'s default `session_id` is evaluated once at import → pass a **fresh**
   `session_id=str(uuid.uuid4())` per send or the server dedups.
3. `AtClient(..., root_address=...)` — always pass it; default is prod.
4. Test env: pull a **fresh** ephemeral image (cert expiry), `--add-host
   vip.ve.atsign.zone:127.0.0.1` (or real VIP), isolate keys with a dedicated `HOME`.

---

## 3. Implementation checklist

### Phase 0 — Foundations ✅ DONE
- [x] Clone the Intel repo (`metro-ai-suite/smart-route-planning-agent`) into this workspace
  → `smart-route-planning-agent/` (sparse clone, release-2026.0.0, 51 files).
- [x] `git init` the working repo; commit the planning docs + spike (commit `68813b1`).
- [x] Provision Atsigns → role map in `config/ee_atsigns.json` (EE NATO atSign + production
  vanity per role). 11 roles incl. policy + policy-admin + commuter.
- [x] Stand up the test env (ephemeral env, fresh image) and onboard all Atsigns →
  `scripts/onboard_all_ee.py` (loops the role map, pulls CRAM, skips already-onboarded).
  **11/11 onboarded** to `HOME=/tmp/eehome`.
- [x] Trust model **decided: a policy engine** (atKeys store + DB-pluggable). Policy atSign
  (`@juliet` / vanity `@route_policy`) provisioned. Build is Phase 2b.

### Phase 1 — Wire contract + cross-language interop ✅ DONE
- [x] Shared contract `src/atsign/wire.py` — the wire IS the `schema.py` Pydantic model
  serialized (`encode`/`decode`/`RECORDS`); `roles.py` resolves role→atSign from config.
- [x] Record names defined (`live_traffic`/`weather`/`traffic_trends`/`planned_events`,
  namespace `smartroute`); `key_name_from_atkey` handles both Dart & atsdk key renderings.
- [x] **Interop spike (critical) — DONE ✅:** Python `atsdk` `notify` → Dart `at_client`
  `subscribe` decrypt, **and** Dart → Python, both verified against a live atServer with
  the `LiveTrafficData` payload intact (see `dart_client/` + `validation/README.md`).
  AES/RSA/IV are interoperable; the cross-language hop is **not** a blocker.

### Phase 2 — Publishers (intersections + conditions feeds) ✅ DONE
- [x] Reusable `AtPublisher` / `AtSubscriber` in `src/atsign/atsign_io.py`
  (IV + fresh-session_id fixes baked in).
- [x] Intersection publisher `atsign/publishers/intersection.py` — emits `LiveTrafficData`
  (cycling density) per intersection role.
- [x] Conditions feed publisher `atsign/publishers/feed.py` — reads the bundled CSVs and
  publishes each row as `WeatherData` / `TrafficTrendsData` / `PlannedEventsData`
  (the CSV read moves from the planner to the data source).
- [x] Each publisher is a standalone, config-driven process (one per role atSign).
- [x] **Acceptance MET:** all 6 publishers push; `scripts/debug_subscriber.py` (planner)
  receives + decrypts + decodes every record into the right model (verified on the EE).

### Phase 2b — Policy plane (the trust model) — **a policy engine** ✅ DONE
- [x] `src/atsign/policy_engine.py` runs as the policy atSign (`@juliet` / `@route_policy`),
  **default-deny**.
- [x] **Rule storage:** `AtKeyPolicyStore` persists grants as **self atKeys in the engine's own
  store** (`rule.<subject>.smartroute`). `PolicyStore` is an interface → a DB-backed impl drops
  in later (NoPorts-style) with no caller change.
- [x] The engine **publishes the authorization set** to the planner (`policy.smartroute`); the
  planner enforces it. (Chose policy-distribution over per-record RPC for performance; the
  enforcement point is the same, so RPC stays an option behind the interface.)
- [x] **Acceptance MET:** with Broadway intentionally not granted, the planner **caches the
  granted publishers and DENIES `@delta` (Broadway)**; re-publishing a new grant set updates
  the planner live (no restart). Verified on the EE.
- [x] **`@route_policy_admin`-signed rule changes** — `dart_client/bin/policy_admin.dart` runs as
  `@kilo`, serves a web policy console (`:8090`), and pushes **versioned** grant changes that the
  engine verifies (sender must be the admin atSign) and applies live. Segregation of duties realized
  (admin `@kilo` ≠ engine `@juliet` ≠ planner `@alpha`).

### Phase 3 — Planner subscriber + `live_traffic.py` SWAP ✅ DONE
- [x] `scripts/planner_subscriber.py` runs as the planner: `start_monitor("smartroute")`,
  drains the queue, caches `live_traffic` (`src/atsign/cache.py`, keyed by source+intersection).
- [x] Each inbound data record is **policy-checked** against the allow-set (from the policy
  engine); unauthorized records are **dropped** (default-deny).
- [x] **SWAP** `controllers/live_traffic.py`: `fetch_route_status()` reads the cache instead of
  `requests.get(...)`. Class, `RouteStatusInterface`, and return type unchanged; original kept
  as `live_traffic.py.intel-orig`.
- [x] **Acceptance MET (data path):** the SWAP'd `LiveTrafficController.fetch_route_status()`
  returns the subscription cache (`['Market St & 1st', '5th Ave & Mission']`) — zero polling,
  no host list, graph untouched.
- [ ] *(Phase 4/5)* full `plan_route` reroute end-to-end — needs intersection coords aligned to
  GPX trackpoints + the OPTIMAL node re-enabled to trigger an actual route change.

### Phase 4 — Re-enable the static optimizers (OPTIMAL node) ✅ DONE
- [x] Re-enabled `STATIC_ROUTE_OPTIMIZER_STACK` in `route_planner.py` (fresh copy so the
  OPTIMAL node's `.pop()` doesn't mutate the global).
- [x] SWAP'd `weather_report.py` / `traffic_trends.py` / `planned_events.py` to read
  `cache.find_condition(...)` (coordinate match, same proximity factors); originals kept
  as `*.intel-orig`.
- [x] `cache.py` extended with conditions caches; planner subscriber caches them.
- [x] **Acceptance MET — genuine live reroute from pushed data** (`scripts/planner_run.py`):
  intersection `@bravo` pushed density=30 at a real trackpoint of the shortest route
  (`berkeley-oakland-i880`); the unmodified LangGraph realtime node rerouted to
  `berkeley-sanbruno` via the SWAP'd `LiveTrafficController` (cache, not a URL).
- [ ] *(optional polish)* force a static-path (weather/event) reroute — wired and
  cache-reading; triggering is data-dependent on feed coords vs route trackpoints.

### Phase 5 — Planner pushes route + reroute alerts ✅ DONE
- [x] `atsign/messages.py` — `RoutePush` / `StatusPush` models + `route_points()` (downsampled geometry).
- [x] Planner `notify()`s the optimal route + reason to the commuter (`route.smartroute`) and
  status to the operator (`status.smartroute`) — in `scripts/planner_run.py`.
- [x] **Acceptance MET:** a reroute computed from pushed data is pushed back —
  `scripts/commuter_receiver.py` got a 🚨 REROUTE ALERT (berkeley-sanbruno, 123 map points),
  `scripts/operator_receiver.py` got the matching status. Verified on the EE.
- [ ] *(Phase 7)* request side: the Flutter app sends start/destination to the planner.

### Phase 6 — Operator Console (reuse Gradio) ✅ DONE
- [x] `atsign/operator_console.py` runs as the operator atSign; an atSign subscriber feeds
  `OperatorState` from the planner's `status.smartroute` pushes (geometry carried in status).
- [x] Reuses Intel's `MapCreator` (Folium) to render the route; Gradio UI built (guarded
  import; launch with `python -m atsign.operator_console`).
- [x] **Acceptance MET:** with the planner pushing a reroute, the console renders the live
  status panel + a Folium/Leaflet map (123 route points, ~14 KB map HTML). Verified headless
  via `scripts/operator_console_test.py`.

### Phase 7 — Commuter Flutter app (`at_client_flutter`) ✅ DONE (code complete)
- [x] Scaffolded `commuter_app/` (Flutter 3.41); deps `at_client_flutter` / `at_client` /
  `at_auth` / `flutter_map` / `latlong2` / `url_launcher`.
- [x] Sign-in screen uses `AtSignSelectionDialog` — pick an **atSign AND root server**
  (production or the `vip.ve.atsign.zone:64` test env, or type a custom domain), then auth
  via device keychain or `.atKeys` file. (Starter-pack gate removed per product direction.)
- [x] Subscribes `route.smartroute` → renders `flutter_map` (OSM tiles) with the route
  polyline + start/end markers + a reroute alert banner.
- [x] Sends start/destination request to the planner (`request.smartroute`).
- [x] **`flutter analyze`: No issues found** (compiles clean).
- [x] Platform permissions added: macOS entitlements (network client/server + user-selected
  file read-only/read-write, Debug + Release), iOS `NSLocalNetworkUsageDescription` + Bonjour,
  Android INTERNET + storage. (Root server is now picked at sign-in.)
- [ ] *(needs a device/simulator)* `flutter run` against the EE (pick `vip.ve.atsign.zone:64`
  + load a commuter's `.atKeys`). Protocol already proven by the interop spike.

### Phase 8 — Packaging, deploy, demo ✅ DONE
- [x] `deploy/Dockerfile` + `deploy/compose.yaml` — one container per atSign role
  (policy, planner, 6 publishers, operator), each mounting only its own keys;
  `ATSIGN_PROFILE` switches EE↔production; `roles.py` honors `ATSIGN_CONFIG`.
- [x] `scripts/run_demo.sh` — one-command live demo (policy → pushed reroute →
  commuter alert + operator status). **Verified end-to-end on the EE.**
- [ ] *(optional)* Path A "act 1" contrast + add-an-intersection-live finale.

### Phase 9 — Hardening & extensibility (high-value slice ✅)
- [x] **Record TTLs:** `cache.py` entries expire (live 60s, conditions 300s) — stale/replayed
  data drops out so the planner reasons over "now". Verified (fresh visible, 120s-old purged).
- [x] **Policy-gated dynamic onboarding demo:** `scripts/onboarding_finale.py` — a new
  intersection (`intxn_downtown` / @lima) is **DENIED** by default-deny, the Policy Admin
  authorizes it, and it **joins the live network with no restart, no config edit**. Verified.
- [ ] *(pilot)* extend policy enforcement to commuter requests + operator viewing; idempotency
  / reconnect-under-failure review.

### Mandatory deliverables (per Atsign implementation rules)
- [x] `ATPLATFORM_GUIDELINES.md` (platform SDK reference — all sections).
- [x] `README.md` (project specifics: Atsign map, namespace, record/payload tables, data flows, run).

---

## 4. Key conventions

| Record (key.namespace) | From → To | Payload (reuses schema.py) |
|------------------------|-----------|----------------------------|
| `live_traffic.smartroute` | intersection → planner | `LiveTrafficData` |
| `weather.smartroute` | weather feed → planner | `WeatherData` |
| `traffic_trends.smartroute` | trends feed → planner | `TrafficTrendsData` |
| `planned_events.smartroute` | events feed → planner | `PlannedEventsData` |
| `route.smartroute` | planner → commuter | `RoutePoints` + distance + reason |
| `status.smartroute` | planner → operator | all routes + intersection states + agent status |
| `authz.smartroute` (RPC) | planner ↔ policy mgr | req `{atSign, role, action}` → resp `allow`/`deny` |

**Policy atSigns:** `@route_policy` (Policy Manager), `@route_policy_admin` (rules owner).

**SDKs:** Python `atsdk` (services) · Dart `at_client` ^3.11 / `at_client_flutter` ^1.0 (commuter app).
**Encryption/identity/no-open-ports:** provided by the platform — not app code.

---

## 5. Open decisions & risks

- **Cross-language encryption interop — RESOLVED ✅** (Python `atsdk` ⇄ Dart `at_client`,
  both directions, proven in the spike). No longer a risk.
- **Trust model — RESOLVED: a Policy *engine*** (`@route_policy`, own Atsign); the planner
  authorizes every publisher/client by identity + role + action, default-deny. Rules stored
  as encrypted atKeys in the engine's own store by default, behind a `PolicyStore` interface
  with a database-backed implementation for scale (NoPorts-style). No flat allow-list file.
- **Atsign provisioning** — vanity vs registered; who owns the service Atsigns long-term.
- **`atsdk` is Beta** — pin the version; keep the two known fixes (IV, session_id); watch for others.
- **Commuter request path** — `notify` vs `put`+`get`; confirm planner reaction latency.


---

## Beyond Phase 9 — delivered since

Recorded here so the plan matches the repo.

### Real-world sensing: a phone as an intersection (`intersection_app/`)

| Item | Detail |
|---|---|
| Goal | Replace a simulated publisher with a real sensor, without touching the planner |
| Approach | Flutter app; camera → ML Kit **object detection** (boxes → count) + **image labeling** (semantic gate: is it a vehicle?); publishes the same `live_traffic.smartroute` record as its own atSign |
| Wire contract | Pinned by unit test to `dart_client/bin/change_route.dart`, so the planner needed no change |
| Demo controls | On-route location presets, density-per-car multiplier (1–50), auto/manual send, Clear, camera switch |
| Verified | `flutter analyze` clean, 12 tests, Android APK builds, and **live**: model cars in view rerouted the planner |
| Not covered by CI | Detection quality itself — it needs a physical device (API 24+) |

Upgrade path documented in `intersection_app/README.md`: a per-object custom TFLite
classifier via `LocalObjectDetectorOptions`, or a COCO/YOLO detector — with the
Ultralytics AGPL-3.0 licensing caveat called out.

### Resilience: surviving network changes

The stack could stop responding after a network change, NAT timeout or laptop sleep.
Root cause: the SDK connects with `settimeout(None)` and reads a byte at a time, so a
peer that goes silent *without closing the connection* blocks reads forever and raises
nothing — our exception-driven reconnects never fired, and a publish inside the planner's
loop froze the whole planner.

| Fix | Where |
|---|---|
| Publishes bounded by a hard deadline, abandoning a stuck send | `AtPublisher.notify` |
| Bounded command-socket reads | `atsign_io._bound_socket_reads` |
| Monitor **liveness watchdog** — heartbeat acks count as liveness, so a quiet namespace is not mistaken for a dead one; true silence force-closes the socket so the reconnect can run | `AtSubscriber` (all subscribers: planner, policy engine, console) |
| Operator console self-heals a wedged subscriber | `operator_console` watchdog |

Reproduced *and* verified against a frozen atServer (`docker pause` — no FIN/RST, like a
real network change): `validation/live_outage_test.py`, plus
`validation/test_subscriber_liveness.py` offline.

### Policy applied consistently

Symptom: a revoked publisher was sometimes still accepted, and an authorization appeared
to take effect only after restarting the whole stack. Three separate causes, all of which
made the rule set ambiguous rather than wrong:

| Cause | Fix |
|-------|-----|
| The engine seeded `granted` from `--grant` (all publishers) on every start and never read back the rules it had persisted, so any restart re-authorised a revoked publisher | `initial_grants()` reads the engine's own rule records; `--grant` seeds only an atSign that has never held rules, and an empty set is honoured as "everything revoked" |
| The admin assumed all-granted and **pushed** that at startup, so starting the stack re-authorised everything | The admin holds no opinion: the engine mirrors its rule set to the admin, and the page renders (and polls) that. Toggling before the engine has spoken is refused |
| `planner_run.py` and `onboarding_finale.py` published their own `policy` record as the policy atSign, overriding the live rule set until the engine's next heartbeat undid it | Both wait for a running engine; the finale asks it through the Policy Admin channel, which is what its script always claimed to do |

Also hardened while in there: a store that cannot be read stops the engine instead of
falling back to `--grant`; a rule that fails to persist is reported instead of silently
diverging from what is being enforced; and a record another atSign *shares* with the
engine can never be read back as a rule.

`start_stack.sh` also **verifies what it started**: it checks each service ~12s in and
tails the log of any that died, rather than printing "stack up" unconditionally. A policy
engine that dies at startup is indistinguishable, from the outside, from a policy that is
never applied — and its log was previously written to `policy.log`, which no
troubleshooting instruction mentioned. It is now `policy_engine.log`.

A rule change is also **confirmed rather than assumed**: the admin treats a toggle as a
request, re-pushes it if the engine has not mirrored it back, and then reports that it was
not applied — quoting the atServer's delivery verdict, which distinguishes "never arrived"
from "arrived and ignored". The engine, in turn, now logs the two cases it used to drop in
silence: a rule set rejected by the monotonic version guard, and publishers it does not
know. A silently discarded change was what made this class of bug so hard to see.

Regression test (network-free): `validation/test_policy_persistence.py`.

### Upstream contributions

Seven fixes merged into `atsign-foundation/at_python` and released in **atsdk 0.2.70 /
0.2.71**, plus an asyncio RFC (#531) still open. Detail and the keep/remove mapping for
our remaining workarounds: [atsdk-upstream-status.md](atsdk-upstream-status.md).
