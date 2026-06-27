# State-flow diagrams — Smart Route Planning on the Atsign Platform

## 1. Planner route decision (Intel's LangGraph graph, reused)

```mermaid
stateDiagram-v2
    [*] --> DirectRoute: request(source, destination)
    DirectRoute: Direct route<br/>shortest GPX route
    StaticOptimize: Static optimize<br/>weather / traffic-trends / events feeds
    RealtimeReroute: Realtime<br/>live intersection traffic
    Monitoring: Monitoring<br/>optimal route held

    DirectRoute --> StaticOptimize
    StaticOptimize --> RealtimeReroute
    RealtimeReroute --> Monitoring: no incident
    RealtimeReroute --> Rerouted: density &gt; threshold on route
    Rerouted: Rerouted<br/>next-best route chosen
    Monitoring --> RealtimeReroute: new live traffic (every cycle)
    Rerouted --> RealtimeReroute: re-evaluate next cycle
```

## 2. Incident lifecycle (what a reroute looks like over time)

```mermaid
stateDiagram-v2
    [*] --> Monitoring
    Monitoring: ✅ Monitoring<br/>optimal = shortest route
    Rerouted: 🚨 Rerouted<br/>incident on shortest route
    Monitoring --> Rerouted: incident pushed<br/>(density &gt; 10 at a route trackpoint)
    Rerouted --> Monitoring: incident cleared (density ≤ 10)
    Rerouted --> Monitoring: record TTL (~60s) expires
    note right of Rerouted
        Planner pushes the new route +
        alert to commuter app & operator console
    end note
```

## 3. Policy-gated dynamic onboarding (a new intersection joins live)

```mermaid
stateDiagram-v2
    [*] --> PoweredOn: new intersection registers an Atsign
    PoweredOn --> Publishing: pushes live_traffic
    Publishing --> Denied: planner default-deny<br/>(not in policy)
    Denied --> Authorized: Policy Admin grants<br/>(identity + role)
    Authorized --> Live: records cached,<br/>influence routing
    Live --> [*]: no restart, no config edit
```

## 4. Subscriber resilience (atSign monitor)

```mermaid
stateDiagram-v2
    [*] --> Connected
    Connected: Monitoring<br/>receiving encrypted pushes
    Connected --> Dropped: heartbeat lost / socket error
    Dropped --> Reconnecting: recreate AtClient
    Reconnecting --> Connected: restart monitor (3s backoff)
```
