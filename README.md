# Smart Route Planning on the Atsign Platform

A migration of Intel's [Smart Route Planning Agent](https://github.com/open-edge-platform/edge-ai-suites/tree/release-2026.0.0/metro-ai-suite/smart-route-planning-agent)
to the Atsign Platform. Intel's LangGraph reasoning is **reused unchanged**; the
transport is replaced with encrypted, port-less, policy-gated identity-to-identity
messaging, and a Flutter commuter app + reused-Gradio operator console are added.

**Docs:** [PRD.md](PRD.md) (non-technical) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) ·
[atsign-migration-assessment.md](atsign-migration-assessment.md) ·
[path-comparison-and-recommendation.md](path-comparison-and-recommendation.md) ·
[blueprints/](blueprints/) · platform reference: [ATPLATFORM_GUIDELINES.md](ATPLATFORM_GUIDELINES.md).

> For the Atsign Platform SDK reference (patterns, init, comms), see
> `ATPLATFORM_GUIDELINES.md`. This file is the **project-specific** reference.

---

## Architecture

```
cameras ─stream→ intersection agents ─┐
                 weather feed         ├─notify(encrypted)→ Smart Route Planner ─┬─push→ Commuter app (Flutter)
                 traffic-trends feed  │   (LangGraph, headless)                 └─push→ Operator console (Gradio)
                 planned-events feed ─┘            │  asks ↑ RPC
                                                Policy Engine (default-deny)
```

- Every participant is an **atSign**. Data flows as encrypted notifications under the
  `smartroute` namespace. No open inbound ports anywhere.
- The planner subscribes to all publishers, **policy-checks** each (default-deny), caches
  the records, runs Intel's unmodified graph, and **pushes** the optimal route + reroute
  alerts to the commuter app and operator console.

## atSign role map (`config/ee_atsigns.json`)

| Role | EE atSign | Production (vanity) |
|------|-----------|---------------------|
| planner | `@alpha` | `@smartroute_planner` |
| intersection — Market St / 5th Ave / Broadway | `@bravo` / `@charlie` / `@delta` | `@intxn_market_st` / `@intxn_5th_ave` / `@intxn_broadway` |
| weather / traffic-trends / events feed | `@echo` / `@foxtrot` / `@golf` | `@weather_feed` / `@traffic_trends_feed` / `@events_feed` |
| operator | `@hotel` | `@route_operator` |
| policy engine / admin | `@juliet` / `@kilo` | `@route_policy` / `@route_policy_admin` |
| commuter | `@india` | `@commuter01` |

Switch profiles with `ATSIGN_PROFILE=ee` (default) or `ATSIGN_PROFILE=vanity`.

## Records (all under the `smartroute` namespace)

| Record | Direction | Payload (model) |
|--------|-----------|-----------------|
| `live_traffic` | intersection → planner | `LiveTrafficData` |
| `weather` | weather feed → planner | `WeatherData` |
| `traffic_trends` | traffic-trends feed → planner | `TrafficTrendsData` |
| `planned_events` | events feed → planner | `PlannedEventsData` |
| `policy` | policy engine → planner | `{grants: [atSign], issued_by}` |
| `route` | planner → commuter | `RoutePush` (route, distance, reason, rerouted, points) |
| `status` | planner → operator | `StatusPush` (+ route geometry) |
| `request` | commuter → planner | `{source, destination}` |

The wire format **is** Intel's `schema.py` Pydantic models serialized to JSON — Python and
Dart interoperate (verified in `spike/`).

## Reuse map (KEEP / SWAP / ADD)

- **KEEP (unchanged):** `agents/route_planner.py` (LangGraph), `planner_state.py`,
  `route_service.py`, `utils/*`, `schema.py`, GPX routes, `map_creator.py`, Gradio patterns.
  *(One line re-enabled in `route_planner.py`: the static-optimizer stack Intel shipped commented out.)*
- **SWAP (read the subscription cache instead of polling/CSV):** `controllers/live_traffic.py`,
  `weather_report.py`, `traffic_trends.py`, `planned_events.py` — class + `RouteStatusInterface`
  unchanged; originals kept as `*.intel-orig`.
- **ADD (new):** `src/atsign/*` (wire, roles, atsign_io, cache, messages, publishers,
  policy_engine, operator_console), `scripts/*`, `commuter_app/` (Flutter).

## Repo layout

```
smart-route-planning-agent/   Intel app (sparse clone) + src/atsign/ integration + SWAP'd controllers
commuter_app/                 Flutter commuter app (at_client_flutter + flutter_map)
scripts/                      onboarding + planner subscriber + receivers + run_demo.sh
config/ee_atsigns.json        role -> atSign map
blueprints/                   Path A (NoPorts) + Path B (native, 16/18) blueprints
spike/                        validated SDK spike + Python<->Dart interop
```

## Run it (local ephemeral environment)

```bash
# 1. Start the EE (fresh image: it ships a valid cert; the cached one may be expired)
docker run -d --name atsign-ee --add-host vip.ve.atsign.zone:127.0.0.1 \
  -e DNS_FQDN=vip.ve.atsign.zone -e FIRST_PORT=2500 \
  -p 64:64 -p 2500-2540:2500-2540 atsigncompany/ephemeral

# 2. One-time: project venv with all deps
python3 -m venv .venv && . .venv/bin/activate
pip install atsdk pydantic langgraph==1.0.9 gpxpy folium "gradio>=6.7.0"

# 3. Set up the terminal (venv + EE keystore + PYTHONPATH) — use a dedicated terminal
source scripts/env.sh

# 4. One-time: onboard the role atSigns
python scripts/onboard_all_ee.py
```

**A. Live system (recommended) — runs continuously:**
```bash
bash scripts/start_stack.sh &                 # policy + planner service + 6 publishers
python -m atsign.operator_console &           # operator web console -> http://127.0.0.1:7865
python scripts/trigger_incident.py            # inject congestion -> console flips to 🚨 REROUTE (clears in ~60s)
bash scripts/stop_stack.sh                     # stop everything
```

**B. One-shot demos (run with the stack stopped — they manage their own policy):**
```bash
bash scripts/run_demo.sh             # policy -> pushed reroute -> commuter alert + operator status
python scripts/planner_run.py        # single reroute + push
python scripts/onboarding_finale.py  # a new intersection joins live (policy-gated)
```

Flutter app: `cd commuter_app && flutter run` — the sign-in screen lets you pick the
**root server** (production or the `vip.ve.atsign.zone` test env) and your atSign.

## Status

Phases 0–6 verified on the EE; Phase 7 (Flutter) analyzes clean; Phase 8 packaging here.
See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the per-phase checklist.
