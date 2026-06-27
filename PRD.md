# Smart Route Planning on the Atsign Platform — Product Brief

*A plain-language overview for non-technical readers. For the build details see
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).*

---

## In one sentence

We are taking Intel's "Smart Route Planning" demo — an AI that guides a driver
around traffic, accidents, floods and road closures in real time — and rebuilding
how its pieces talk to each other so the whole system is **private, secure, and
able to grow**, using the Atsign Platform.

## What it does (the experience)

- A **driver** opens a phone app, picks where they're going, and sees the best route.
- Behind the scenes, **smart traffic intersections** and **data feeds** (weather,
  historical traffic, planned events like concerts or games) constantly report
  conditions.
- An **AI route planner** weighs all of that and, the moment a road becomes a bad
  idea (a flood, a crash, heavy congestion), it **pushes a new route to the driver's
  phone instantly** — with an alert explaining why.
- A **city operator** watches the whole network on a control-room dashboard: every
  intersection, every active route, and the AI's reasoning.

## The problem with the demo as it stands

Intel's version works on a single computer, but it wasn't built to leave that
computer safely:

- **Every traffic intersection has to leave a "door" open** on the internet for the
  planner to reach it. Open doors are exactly what attackers look for.
- **Nothing is private or verified** — the connections aren't encrypted, and there's
  no built-in proof of who is who.
- **Adding a new intersection means editing a list by hand** — it doesn't scale to a
  real city.
- **There's no real driver app** — today it's a web page on the same machine, with no
  notion of "my route" for an individual person.
- Some of the planned capabilities (reacting to weather and events) **ship turned off**.

## What we're changing

We give **every participant its own secure digital identity** (an "atSign") — each
intersection, each data feed, the planner, the operator, and each driver. Then:

- **No open doors.** Devices only ever reach *out*; nothing sits waiting to be
  attacked. There is nothing to port-scan.
- **Private and verified by default.** Every message is encrypted end-to-end and is
  provably from who it claims to be — no passwords, no accounts.
- **Push instead of poll.** Intersections and feeds *push* updates the instant
  something changes, so the driver's phone reacts in real time — even in their pocket.
- **Grows by itself — but only with permission.** A new intersection switches on with
  its own identity and starts contributing — no list to edit, no planner change — *once
  it's approved* (see the rulebook below).
- **One central security rulebook (the "policy plane").** A dedicated security role
  decides, in one place, which intersections, feeds, drivers and operators are allowed to
  take part and what each may do. The planner checks this rulebook before trusting anyone,
  so nothing can quietly join uninvited, and the people running day-to-day operations are
  kept separate from the people who set security rules. (This mirrors how Atsign's NoPorts
  product controls access.)
- **Turns the dormant features back on.** Weather, historical-traffic and planned-event
  awareness become live, first-class inputs again.

## Who uses it, and what they see

| Person | What they use | What they see |
|--------|---------------|---------------|
| **Driver / commuter** | A phone app | Their route on a map; live "re-routing — flood ahead" style alerts |
| **City operator** | A control-room dashboard | The whole network: all intersections, all routes, why the AI rerouted |
| **Security / policy admin** | A simple rules screen | Who is allowed to publish data, request routes, or view the network — set in one place |

## How it works, simply

1. Intersections and data feeds each **publish** what they see to the planner —
   securely, addressed by identity, never by exposing themselves to the open internet.
2. The **AI planner** (Intel's existing "brain", reused as-is) combines everything and
   picks the best route.
3. The planner **pushes** that route — and any later changes — straight to the driver's
   phone and the operator's dashboard.
4. If conditions change, steps 1–3 repeat automatically and the driver is re-routed on
   the spot.

## Why this is the right approach

- **We keep Intel's smarts.** The AI route-planning logic is reused unchanged; we only
  replace *how the pieces communicate*. Lower risk, faster to demo.
- **Security is built in, not bolted on.** Encryption and identity come from the
  platform, so there's far less that can be misconfigured.
- **It tells a real city-scale story.** Distributed intersections, a mobile driver
  experience, and live expansion — the things a single-machine demo can't show.

## What we reuse vs. build new

- **Reuse (most of it):** the AI planner, the route/map logic, the existing dashboard
  (repurposed as the operator console), and the sample data so it runs on day one.
- **Build new (small, well-scoped):** the secure "publish/subscribe" plumbing between
  identities, and a polished **driver phone app**.

## The demo

- **Act 1 (optional opener):** show the existing app hardened with *no code rewrite* —
  every connection secured, no open doors.
- **Act 2 (the main event):** the full experience on two screens — a **driver's phone**
  and the **operator dashboard**. Trigger a flood on a route and watch the phone
  re-route and alert instantly. Then **switch on a brand-new intersection live** and
  watch it join the network with zero configuration.

## High-level milestones

1. **Foundations** — set up the secure identities and a safe test environment.
2. **Plumbing** — the intersections and feeds publish; the planner listens. *(Proven
   already in a working spike.)*
3. **Smarts back on** — re-enable weather/traffic/event awareness.
4. **Live driver experience** — the phone app with real-time re-routing and alerts.
5. **Operator dashboard** — the control-room view.
6. **Polish & demo** — packaging, the runbook, and the "add an intersection live" finale.

## What "done" looks like (success criteria)

- A driver on a real phone receives a route and is **re-routed live** when conditions change.
- The operator dashboard reflects the whole network in real time.
- **No internet-facing open ports** anywhere in the system.
- A **new intersection can be added live** with no configuration change.
- Intel's AI planning logic is **reused unchanged**.

## Plain-language glossary

- **atSign** — a secure digital identity (like `@smartroute_planner`). The unit of
  "who" in the system; it replaces accounts and passwords.
- **Edge AI** — software running *at* the intersection (on local cameras) rather than in
  a faraway data center.
- **Publish / subscribe** — sources announce updates; interested parties receive them
  automatically — like following a channel rather than repeatedly asking "anything new?".
- **End-to-end encrypted** — only the intended recipient can read a message; nobody in
  between can.
- **No open ports** — the devices never leave a "door" open to the internet, removing a
  whole category of attacks.
- **Namespace** — a label (`smartroute`) that keeps this app's data tidy and separate.
- **Policy plane** — a central rulebook (and the service, or "policy engine", that enforces
  it) that decides who is allowed to do what. Lets a security team control access in one
  place, kept separate from day-to-day operations. The rules are kept securely under the
  policy's own identity and can scale to a database. Modeled on Atsign's NoPorts policy manager.
