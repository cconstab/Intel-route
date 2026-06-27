# Implementation Plan — Smart Route Planning on the Atsign Platform (Path B)

**Source of truth:** [blueprints/path-b-native-atsign.blueprint.json](blueprints/path-b-native-atsign.blueprint.json)
(14 nodes / 16 edges, validated). Companion docs: [PRD.md](PRD.md) ·
[atsign-migration-assessment.md](atsign-migration-assessment.md) ·
[path-comparison-and-recommendation.md](path-comparison-and-recommendation.md) ·
spike: [spike/README.md](spike/README.md).

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

### Spike learnings already baked in (see `spike/publisher.py`)
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
  the `LiveTrafficData` payload intact (see `spike/interop_dart/` + `spike/README.md`).
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

### Phase 2b — Policy plane (the trust model) — **a policy engine, not a flat allow-list**
- [ ] Build the **Policy Manager** as a **policy engine** (`@route_policy`, own Atsign):
  answers *may `<atSign>` act as `<role>` for `<action>` (publish / request / view)?* — **default-deny**.
- [ ] **Rule storage:** store policies as **encrypted records (atKeys) in the engine's own
  Atsign store** by default — they sync automatically and need no external DB to run.
  Put storage behind a `PolicyStore` interface with a second **database-backed**
  implementation (NoPorts-style) for scale.
- [ ] Rule model: `{subject Atsign, role, action, resource, allow}` — evaluated in order, default-deny.
- [ ] **Policy Admin** (`@route_policy_admin`) writes/edits rules (CLI or small UI) into the store.
- [ ] Expose evaluation as request/response (Dart `AtRpc` / equivalent request key in Python),
  with a short-TTL decision cache on the planner.
- [ ] **Acceptance:** planner authorizes a known publisher and **rejects an unknown one**;
  adding a rule (atKey) takes effect live without restarting the planner; the same rules
  work unchanged when swapped to the DB-backed store.

### Phase 3 — Planner subscriber + `live_traffic.py` SWAP
- [ ] Add an atsdk **subscriber** module in the planner: `start_monitor("smartroute")`,
  drain queue → in-memory cache keyed by `(source-atsign, intersection/point)`.
- [ ] On each inbound record, **check the Policy Manager** (cached, TTL) that the sender is
  an authorized publisher; drop unauthorized records.
- [ ] **SWAP** `controllers/live_traffic.py`: `fetch_route_status()` reads the cache
  instead of `requests.get(...)`. Signature + `RouteStatusInterface` unchanged.
- [ ] Map cache entries → `LiveTrafficData` exactly as before (graph untouched).
- [ ] **Acceptance:** planner produces a route from pushed live-traffic with zero polling
  and no `config.json` host list.

### Phase 4 — Re-enable the static optimizers (OPTIMAL node)
- [ ] Re-enable `STATIC_ROUTE_OPTIMIZER_STACK` in `route_planner.py` (Intel left it
  commented out).
- [ ] Point the weather/traffic/events controllers at the subscription cache (fed by the
  feed Atsigns) instead of reading CSVs directly — same `RouteStatusInterface`.
- [ ] **Acceptance:** a weather/event feed value changes the chosen route (not just density).

### Phase 5 — Planner pushes route + reroute alerts
- [ ] Planner `notify()`s the optimal route geometry (`RoutePoints`) + reason to each
  subscribed commuter Atsign (`route.smartroute`) and to `@route_operator` (`status.smartroute`).
- [ ] Handle the request side: commuter app `notify`/`put` start+destination →
  planner reacts (Phase 7 wires the client).
- [ ] **Acceptance:** changing conditions pushes an updated route to subscribers in real time.

### Phase 6 — Operator Console (reuse Gradio)
- [ ] Run Intel's `main.py` Gradio UI as `@route_operator`; replace its internal queue
  source with an atsdk subscriber to the planner's `status.smartroute` pushes.
- [ ] Keep `map_creator.py` / Folium rendering unchanged.
- [ ] **Acceptance:** operator sees all active routes, intersections, agent reasoning, live.

### Phase 7 — Commuter Flutter app (`at_client_flutter`)
- [ ] Scaffold from the `at_client_flutter` example app (main.dart + walkthrough.dart).
- [ ] **MANDATORY first-run Atsign gate** (per implementation rules) → then the 4 auth
  workflows (keychain / registrar onboarding / APKAM / .atKeys file).
- [ ] Subscribe to `route.smartroute`; render route on a map widget; pop reroute alerts.
- [ ] Send start/destination to `@smartroute_planner`.
- [ ] Platform permissions (macOS entitlements, iOS Info.plist, Android manifest) per rules.
- [ ] **Acceptance:** on a real phone, request a route and watch it re-route + alert live.

### Phase 8 — Packaging, deploy, demo
- [ ] `compose.yaml` per service (planner, 6 publishers, operator) each with its Atsign +
  unique hive/commit-log paths.
- [ ] Demo runbook: Act 1 (Path A contrast, optional) → Act 2 (Path B: two screens,
  trigger flood, add a 4th intersection live).
- [ ] **Acceptance:** clean-machine bring-up from the runbook.

### Phase 9 — Hardening & extensibility
- [ ] Enforce **Policy-Manager decisions** on every publish / request / view (cache + TTL).
- [ ] Demonstrate **policy-gated** dynamic onboarding: a new `@intxn_*` is rejected until
  the Policy Admin authorizes it, then joins live with no planner change.
- [ ] TTLs on all records; reconnect/idempotency review.

### Mandatory deliverables (per Atsign implementation rules)
- [ ] `ATPLATFORM_GUIDELINES.md` (platform SDK reference — all sections, verbatim).
- [ ] `README.md` (project specifics: Atsign map, namespace, record/payload tables, data flows).

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
