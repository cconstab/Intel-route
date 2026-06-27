#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Phase 4 end-to-end demo (single process for deterministic orchestration; in
production these atSigns live on separate machines).

- @alpha subscribes (cache + policy enforcement).
- @route_policy publishes a grant set (default-deny otherwise).
- @intxn_market_st publishes a HIGH-density live_traffic record at a REAL trackpoint
  of the current shortest route.
- The unmodified Intel LangGraph node `update_optimal_route_realtime` runs on the
  pushed data (via the SWAP'd LiveTrafficController) and **reroutes** off the
  blocked route — a genuine live reroute from an encrypted push, no polling.

Run:  python scripts/planner_run.py
"""
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from config import DEFAULT_LOCATIONS, IGNORED_ROUTES, GPX_DIR, WeatherStatus, IncidentStatus  # noqa: E402
from schema import GeoCoordinates, LiveTrafficData  # noqa: E402
from agents.route_planner import RoutePlanner  # noqa: E402
from utils.gpx_parser import MapDataParser  # noqa: E402
from atsign import roles, wire, cache, messages  # noqa: E402
from atsign.atsign_io import AtPublisher, AtSubscriber  # noqa: E402

ALLOW: set = set()
POLICY_SOURCE = roles.atsign_for("policy")


def on_record(frm, key, value, raw):
    kn = wire.key_name_from_atkey(key)
    if kn == "policy":
        if frm == POLICY_SOURCE:
            ALLOW.clear()
            ALLOW.update(json.loads(value).get("grants", []))
            print(f"[planner] POLICY: authorized = {sorted(ALLOW)}")
        return
    if frm not in ALLOW:
        print(f"[planner] DENIED {kn} from {frm}")
        return
    if kn == "live_traffic":
        cache.put_live_traffic(frm, wire.decode(kn, value))
        print(f"[planner] CACHED live_traffic from {roles.role_for_atsign(frm)} (cache={cache.size()})")


def wait_for(predicate, what, timeout=30):
    for _ in range(timeout * 2):
        if predicate():
            return True
        time.sleep(0.5)
    print(f"[planner] TIMEOUT waiting for {what}")
    return False


def main():
    me = roles.atsign_for("planner")
    print(f"[planner] starting as {me}")
    sub = AtSubscriber(me, roles.namespace(), on_record)
    threading.Thread(target=sub.start, daemon=True).start()
    time.sleep(3)

    # Policy: grant the Market St intersection (default-deny otherwise).
    AtPublisher(POLICY_SOURCE).notify(
        me, "policy",
        json.dumps({"grants": [roles.atsign_for("intxn_market_st")], "issued_by": POLICY_SOURCE}),
    )
    wait_for(lambda: ALLOW, "policy")

    # Find the current shortest route and a real trackpoint on it.
    src, dst = DEFAULT_LOCATIONS[0], DEFAULT_LOCATIONS[-1]
    rp = RoutePlanner()
    shortest, dist = rp._find_new_shortest_available_route(src, dst, list(IGNORED_ROUTES))
    print(f"\n[planner] shortest direct route: {shortest} ({dist:.1f} km)")
    tps = MapDataParser(GPX_DIR / shortest).get_route_data()["tracks"][0]["track_points"]
    tp = tps[len(tps) // 2]
    lat, lon = tp["lat"], tp["lon"]
    print(f"[planner] blocking a real trackpoint on it: ({lat}, {lon})")

    # The intersection pushes a HIGH-density live record at that exact trackpoint.
    rec = LiveTrafficData(
        location_coordinates=GeoCoordinates(latitude=lat, longitude=lon),
        intersection_name="Market St & 1st",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        traffic_density=30,  # > threshold (10)
        traffic_description="severe congestion (pushed)",
        weather_status=WeatherStatus.CLEAR,
        incident_status=IncidentStatus.CROWDING,
    )
    AtPublisher(roles.atsign_for("intxn_market_st")).notify(me, "live_traffic", wire.encode(rec))

    def my_record_cached():
        return any(
            r.location_coordinates.latitude == lat and r.location_coordinates.longitude == lon
            for r in cache.get_live_traffic()
        )
    wait_for(my_record_cached, "my live-traffic record at the trackpoint")

    # Run the UNMODIFIED Intel realtime node on the pushed data.
    print("\n[planner] running LangGraph realtime node on pushed live traffic ...")
    state = {
        "source": src, "destination": dst,
        "optimal_route": {"route_name": shortest, "distance": dist},
        "no_fly_list": list(IGNORED_ROUTES),
    }
    result = rp.update_optimal_route_realtime(state)
    new_route = result["optimal_route"]["route_name"]
    lt = result.get("live_traffic", {})
    rerouted = bool(new_route) and new_route != shortest
    chosen = new_route or shortest
    chosen_dist = result["optimal_route"].get("distance", dist)
    reason = (
        f"Severe congestion at {lt.get('intersection_name')} "
        f"(density {lt.get('traffic_density')}) — rerouted"
        if rerouted else "No incidents on the optimal route"
    )

    print("\n==================== RESULT ====================")
    print(f"  shortest direct route : {shortest}")
    print(f"  realtime optimal route: {new_route}")
    print(f"  REROUTED              : {rerouted}")
    print(f"  triggered by          : {lt.get('intersection_name')} density={lt.get('traffic_density')}")

    # Phase 5: PUSH the chosen route to the commuter app and status to the operator console.
    planner_pub = AtPublisher(me)
    route_push = messages.RoutePush(
        route_name=chosen, distance_km=chosen_dist, reason=reason,
        rerouted=rerouted, points=messages.route_points(chosen),
    )
    planner_pub.notify(roles.atsign_for("commuter01"), "route", route_push.model_dump_json())
    status_push = messages.StatusPush(
        optimal_route=chosen, distance_km=chosen_dist, reason=reason, rerouted=rerouted,
        agent_status="Active - rerouted" if rerouted else "Active - monitoring",
        intersections=[{"name": lt.get("intersection_name"), "density": lt.get("traffic_density")}] if lt else [],
    )
    planner_pub.notify(roles.atsign_for("operator"), "status", status_push.model_dump_json())
    print(f"  PUSHED route -> {roles.atsign_for('commuter01')} | status -> {roles.atsign_for('operator')}")
    print("  (reroute computed from an encrypted push; route pushed back, no polling, no open ports)")
    time.sleep(2)  # let pushes flush
    os._exit(0)


if __name__ == "__main__":
    main()
