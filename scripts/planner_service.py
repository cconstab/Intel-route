#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Long-running planner service (the real backend for the live stack).

Subscribes to `smartroute` (cache + policy enforcement, default-deny), and on a
timer runs Intel's unmodified realtime node over the cache, then PUSHES the
optimal route to the commuter and status to the operator. Trigger a reroute with
`scripts/trigger_incident.py`. Unlike `planner_run.py`, this does NOT publish its
own policy — it relies on the running policy engine, so it composes with the stack.

Run:  python scripts/planner_service.py
"""
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from config import DEFAULT_LOCATIONS, IGNORED_ROUTES  # noqa: E402
from agents.route_planner import RoutePlanner  # noqa: E402
from atsign import roles, wire, cache, messages  # noqa: E402
from atsign.atsign_io import AtPublisher, AtSubscriber  # noqa: E402

POLICY = roles.atsign_for("policy")
ALLOW: set = set()
_denied_seen: dict = {}  # source -> last-logged monotonic time (throttle denial spam)


def on_record(frm, key, value, raw):
    kn = wire.key_name_from_atkey(key)
    if kn == "policy":
        if frm == POLICY:
            new_allow = set(json.loads(value).get("grants", []))
            revoked = ALLOW - new_allow
            ALLOW.clear()
            ALLOW.update(new_allow)
            # Purge cached data from any just-revoked publisher so revocation takes
            # effect this cycle — otherwise its incident lingers until TTL and the
            # planner keeps rerouting on data from a now-denied source (flicker).
            for src in revoked:
                dropped = cache.drop_source(src)
                print(f"[planner-service] policy revoked {src}; purged {dropped} cached record(s)")
            print(f"[planner-service] policy applied; ALLOW = {sorted(ALLOW)}", flush=True)
        return
    if frm not in ALLOW:
        # default-deny: record from a non-granted publisher. Log (throttled per source)
        # so enforcement is VISIBLE instead of a silent drop.
        now = time.monotonic()
        if now - _denied_seen.get(frm, 0) > 10:
            _denied_seen[frm] = now
            print(f"[planner-service] DENIED {kn} from {frm} (not granted — dropped)", flush=True)
        return
    if kn == "live_traffic":
        cache.put_live_traffic(frm, wire.decode(kn, value))
    elif kn in ("weather", "traffic_trends", "planned_events"):
        cache.put_condition(kn, frm, wire.decode(kn, value))


def main():
    me = roles.atsign_for("planner")
    threading.Thread(
        target=lambda: AtSubscriber(me, roles.namespace(), on_record).start(), daemon=True
    ).start()
    time.sleep(6)  # let the @alpha connection establish before opening a 2nd client (avoids a root-conn race)
    pub = AtPublisher(me)
    rp = RoutePlanner()
    src, dst = DEFAULT_LOCATIONS[0], DEFAULT_LOCATIONS[-1]
    print(f"[planner-service] {me} running; planning every 8s, pushing to commuter+operator")
    last = None

    while True:
        time.sleep(8)
        try:
            shortest, dist = rp._find_new_shortest_available_route(src, dst, list(IGNORED_ROUTES))
            if not shortest:
                continue
            state = {
                "source": src, "destination": dst,
                "optimal_route": {"route_name": shortest, "distance": dist},
                "no_fly_list": list(IGNORED_ROUTES),
            }
            # Reset Intel's cross-call buffer so each cycle reflects only the current cache
            # (avoids stale-incident flapping when calling the node in a loop).
            rp.live_traffic_status_list = []
            result = rp.update_optimal_route_realtime(state)
            chosen = result["optimal_route"].get("route_name") or shortest
            cdist = result["optimal_route"].get("distance", dist)
            lt = result.get("live_traffic", {})
            rerouted = bool(lt) and chosen != shortest
            reason = (
                f"Severe congestion at {lt.get('intersection_name')} (density {lt.get('traffic_density')})"
                if rerouted else "No incidents on the optimal route"
            )
            pts = messages.route_points(chosen)
            pub.notify(roles.atsign_for("commuter01"), "route", messages.RoutePush(
                route_name=chosen, distance_km=cdist, reason=reason, rerouted=rerouted, points=pts,
            ).model_dump_json())
            pub.notify(roles.atsign_for("operator"), "status", messages.StatusPush(
                optimal_route=chosen, distance_km=cdist, reason=reason, rerouted=rerouted,
                agent_status="Active - rerouted" if rerouted else "Active - monitoring",
                intersections=[{"name": lt.get("intersection_name"), "density": lt.get("traffic_density")}] if lt else [],
                points=pts,
            ).model_dump_json())
            if chosen != last:
                print(f"[planner-service] optimal={chosen} rerouted={rerouted} ({reason})")
                last = chosen
        except Exception as e:
            print(f"[planner-service] loop error: {e}")


if __name__ == "__main__":
    main()
