# Migrating the Intel Smart Route Planning Agent to the Atsign Platform

**Assessment & migration approach**

- Source use case: <https://docs.openedgeplatform.intel.com/2026.0/edge-ai-suites/smart-route-planning-agent/index.html>
- Source code: <https://github.com/open-edge-platform/edge-ai-suites/tree/release-2026.0.0/metro-ai-suite/smart-route-planning-agent>
- Date: 2026-06-26

---

## 1. What this use case actually is

A **Route Planning Agent** — a Python / Gradio app built on a LangGraph state machine that, given a source and destination:

1. Picks the shortest GPX route from a small set of pre-baked routes.
2. Optimizes it against *static* data — weather / traffic / planned-events CSVs (currently disabled in code).
3. Continuously re-optimizes in **real time** by pulling **live traffic data from "Smart Traffic Intersection Agents"** and routing around congestion and incidents.

The "intersection agents" are a **separate component** (Intel's Scene Intelligence / Smart Intersection app, *not* contained in this repo). This repository is only the planner plus its Gradio UI.

### Component map (this repo)

| Area | File | Role |
|------|------|------|
| UI / app loop | `src/main.py` | Gradio UI on port 7860 (7864 host); background thread invokes the agent every ~12s |
| Agent | `src/agents/route_planner.py` | LangGraph graph: `direct` → `optimal` → `realtime` nodes |
| Live traffic transport | `src/controllers/live_traffic.py` | **HTTP polling of intersection agents** |
| Transport config | `src/data/config.json` | Static list of intersection host URLs |
| Schema | `src/schema.py` | `LiveTrafficData`, `WeatherData`, etc. (Pydantic) |
| Deployment | `src/compose.yaml`, `src/Dockerfile` | Single container, docker compose |

---

## 2. Key finding: the "multi-agent communication" is HTTP polling of hardcoded localhost ports

This is the part that matters for an Atsign migration. Despite the "multi-agent communication model" framing in the docs, the actual mechanism is plain HTTP — in `src/controllers/live_traffic.py`:

```python
for api_host in config.get("api_hosts", []):
    http_response = requests.get(f"{host}{api_endpoint}")
```

driven by `src/data/config.json`:

```json
{
  "api_endpoint": "/api/v1/traffic/current?images=false",
  "api_hosts": [
    {"host": "http://localhost:8081"},
    {"host": "http://localhost:8082"},
    {"host": "http://localhost:8083"}
  ]
}
```

So today the entire inter-agent transport is: **plain-HTTP `GET` polling, every ~12s, against a static list of `localhost` ports.**

### Limitations the moment you leave a single demo box

| Limitation | Detail |
|-----------|--------|
| **Open inbound ports** | Every intersection must expose a listening port (8081, 8082…) → firewall holes, NAT traversal, VPNs, an attack surface per intersection. |
| **No encryption / no auth** | Uses `http://` with no tokens. Fine for `localhost`, unacceptable across a metro. |
| **Static discovery** | Hosts hardcoded in JSON; no way to add, move, or retire intersections dynamically. |
| **Pull / poll model** | The planner must know and reach every intersection; intersections cannot push updates. |

These four limitations are exactly Atsign's wheelhouse.

---

## 3. Why this is a strong Atsign fit

The atPlatform directly removes all four limitations:

- **No open inbound ports** — intersections only connect *out* to their atServer; nothing listens at the edge.
- **End-to-end encrypted** by default — every payload is encrypted between atSigns.
- **atSign-based addressing & discovery** — `@intersection_xyz` instead of `IP:port`; no host list to maintain.
- **Native notify / subscribe** — replaces polling with an event-driven push model.

Each intersection becomes an atSign (e.g. `@intersection_market_5th`), the planner becomes `@routeplanner`, and the wire is encrypted with no listening sockets on the edge devices.

---

## 4. Migration paths

### Path A — NoPorts drop-in (lowest effort, ~1 file)

Keep `live_traffic.py` and the REST API as-is. Replace each `http://localhost:808x` with a NoPorts-forwarded local socket that tunnels to the remote intersection's atSign. The planner still thinks it is hitting localhost; in reality each call rides an encrypted, port-less atProtocol tunnel.

- **Effort:** minimal — config change plus NoPorts tunnels per intersection.
- **Story:** "You don't even have to rewrite the app to harden and distribute it."

### Path B — Native atProtocol notify / pubsub (showcase)

Replace the REST `GET` entirely. Intersection agents **publish** `LiveTrafficData` as encrypted notifications to subscribers; the planner **subscribes** and maintains a live cache instead of polling.

- **Effort:** higher — reimplement `fetch_route_status()` against an atClient SDK, plus a small publisher shim on the intersection side (likely simulated, since that component isn't in this repo).
- **Story:** event-driven, scales to N intersections with no host list — the true "agent-to-agent" story the Intel docs only gesture at.

### Recommendation

**Build B as the demo, but lead the pitch with A.** A is the "no rewrite required" hook; B is the "and here's what it looks like done right" payoff. The integration surface is tiny and well-isolated (`live_traffic.py` + `config.json`), so both are very achievable.

---

## 5. Open questions to pin down before building

1. **Which atSign SDK?** This app is Python. Use a Python atClient, or wrap a Dart / NoPorts binary? This drives Path B effort significantly.
2. **The intersection side.** The Scene Intelligence agent isn't in this repo. Do we have access to it, or do we build a mock publisher emitting the same `/api/v1/traffic/current` JSON shape?
3. **Demo scope.** Transport replacement only, or also show dynamic intersection onboarding (a new `@intersection` appearing without editing config)?

---

## 6. Suggested next steps

- [ ] Fetch the Intel Scene Intelligence intersection-agent API spec (the `/api/v1/traffic/current` response shape).
- [ ] Decide Python atClient vs NoPorts wrapper (Q1).
- [ ] Sketch concrete code changes for Path A and/or Path B.
- [ ] Build a mock intersection publisher if the real one is unavailable.
