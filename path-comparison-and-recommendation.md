# Smart Route Planning on Atsign — Path A vs Path B, and what to demo

**Companion to** [atsign-migration-assessment.md](atsign-migration-assessment.md).
Raw blueprints live in [blueprints/](blueprints/).
Date: 2026-06-26

---

## TL;DR recommendation

**Build Path B (native pub/sub) as the flagship demo, and use Path A (NoPorts drop-in) as the opening act.**

- **Path A** is the *risk-reducer*: it proves you can harden and distribute the existing Intel app with ~0 application-code change. Great first impression, ~minutes of effort.
- **Path B** is the *payoff*: it shows the native Atsign value — port-less encrypted pub/sub, identity-based discovery, and live extensibility (add an intersection with no config edit). This is the "demonstrable **and** extensible" system the project is aiming for.

Most engineering effort goes into B. A is nearly free and makes B's value land harder by contrast.

---

## Side-by-side

| | **Path A — NoPorts drop-in** | **Path B — Native pub/sub** |
|---|---|---|
| Blueprint | [`blueprints/path-a-noports-dropin.blueprint.json`](blueprints/path-a-noports-dropin.blueprint.json) | [`blueprints/path-b-native-atsign.blueprint.json`](blueprints/path-b-native-atsign.blueprint.json) |
| Transport | Encrypted tunnel carrying the existing request/response | Encrypted push notifications (publish/subscribe) |
| Edge direction | Planner **polls** agents (→) | Agents **push** to planner (←) |
| `live_traffic.py` | **KEEP** — untouched | **SWAP** — body reads a subscription-fed cache |
| `config.json` | One edit: host URLs → local tunnel sockets | Replaced by a namespace subscription |
| Intersection code | **Zero change** — existing service as-is | New publisher (reuses `schema.py`) |
| Open inbound ports | None (incl. the UI) | None |
| App code changed | ~0 lines | Comms layer only |
| Discovery / onboarding | Add one host entry + a tunnel per intersection | New intersection = new Atsign in the namespace, **no config edit** |
| Weather / traffic / events | Stay as Intel's local CSVs (still disabled) | Become their own publishing Atsigns; **re-enables** the dormant `OPTIMAL` node |
| Commuter surface | Reused Gradio web page | **Flutter mobile app** (`@commuter01`) with pushed reroute alerts |
| Front-ends | Gradio (single shared session) | **Flutter commuter app** + Gradio reframed as **Operator Console** (`@route_operator`) |
| Effort | Very low | Moderate (isolated to one seam) |
| Best at showing | "Harden what exists, no rewrite" | "What it looks like done right + extensibility" |

---

## When to pick each

**Pick Path A if** the audience cares about migration friction and risk: "we have a working app today, prove Atsign secures and distributes it without touching our code." It also works as a fallback if SDK/time constraints bite.

**Pick Path B if** the audience cares about the architecture story: removing the static host list, identity-based discovery, push instead of poll, and turning every data source (weather, events, traffic trends) into an independent publisher you can add or swap live.

---

## Recommended demo narrative (use both)

1. **Act 1 — Path A (≈2 min).** Show the unmodified Intel app running. Point out it polls `localhost:8081/8082/8083`. Flip `config.json` to tunnel sockets; the intersections now run on separate hosts with **no open ports**, end-to-end encrypted, and the app is none the wiser. *Message: zero-rewrite hardening.*
2. **Act 2 — Path B (the main event).** Switch to the native build with **two screens**: a **Flutter commuter app on a real phone** and the **Gradio operator console** (control-room view) side by side. Intersections **push** updates; the planner subscribes by namespace and **pushes the route + reroute alerts to the phone**. Trigger a flood/accident on a route and watch the phone re-route and alert in real time. Then **add a 4th intersection live** — register its Atsign, start its publisher — and watch it appear with no config change and no restart. *Message: native, secure, extensible, and tangible.*

---

## Effort & risk notes

- **Shared seam:** both paths touch only `live_traffic.py` + `config.json`. The LangGraph agent, Gradio UI, mapping, GPX parsing, and `schema.py` are reused untouched in both.
- **Biggest open question (Path B):** the Python Atsign SDK choice (native atClient vs wrapping a Dart/NoPorts binary). This drives most of B's effort — resolve before committing.
- **Intersection side is not in the Intel repo** for either path. A needs a tunnel in front of the (separate) Scene Intelligence service; B needs a small publisher. For the demo, both can be driven by the bundled CSVs.
- **Trust model (Path B):** namespace-wide subscription is the extensibility win but means trusting any Atsign publishing in `.smartroute`. Decide whether to add an allow-list of authorized intersection Atsigns.

---

## Next steps

- [ ] Decide Python Atsign SDK approach (gates Path B).
- [ ] Confirm demo Atsigns (vanity vs registered) — see suggested names below.
- [ ] Build the CSV-driven publisher (reusable for live-traffic, weather, traffic-trends, planned-events).
- [ ] Implement the `live_traffic.py` cache-read swap + subscriber (Path B), or the tunnel config (Path A).

### Suggested Atsigns (both blueprints)

| Role | Atsign |
|------|--------|
| Planner | `@smartroute_planner` |
| Intersections | `@intxn_market_st`, `@intxn_5th_ave`, `@intxn_broadway` |
| Conditions feeds (Path B) | `@weather_feed`, `@traffic_trends_feed`, `@events_feed` |
| Commuter (Flutter app) | `@commuter01` |
| Operator console (Path B) | `@route_operator` |
| Namespace | `.smartroute` |
