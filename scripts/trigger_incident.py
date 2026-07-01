#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Inject a severe-congestion incident at a real trackpoint of the current shortest
route (published by the Market St intersection atSign). The running planner service
reroutes on its next cycle; the operator console + commuter app flip to 🚨 REROUTE.
The incident self-clears when its record TTL (60s) expires.

Run (stack must be running):  python scripts/trigger_incident.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from config import DEFAULT_LOCATIONS, IGNORED_ROUTES, GPX_DIR, WeatherStatus, IncidentStatus  # noqa: E402
from schema import GeoCoordinates, LiveTrafficData  # noqa: E402
from agents.route_planner import RoutePlanner  # noqa: E402
from utils.gpx_parser import MapDataParser  # noqa: E402
from atsign import roles, wire  # noqa: E402
from atsign.atsign_io import AtPublisher  # noqa: E402


def main():
    src, dst = DEFAULT_LOCATIONS[0], DEFAULT_LOCATIONS[-1]
    rp = RoutePlanner()
    shortest, _ = rp._find_new_shortest_available_route(src, dst, list(IGNORED_ROUTES))
    tps = MapDataParser(GPX_DIR / shortest).get_route_data()["tracks"][0]["track_points"]
    tp = tps[len(tps) // 2]
    rec = LiveTrafficData(
        location_coordinates=GeoCoordinates(latitude=tp["lat"], longitude=tp["lon"]),
        intersection_name="Incident (injected)",  # distinct key so it doesn't get overwritten
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        traffic_density=30, traffic_description="severe congestion (injected)",
        weather_status=WeatherStatus.CLEAR, incident_status=IncidentStatus.CROWDING,
    )
    # Re-send a few times with a short delay. A one-shot Python notify can be dropped
    # by the receiver the FIRST time it sees this sender (atsdk shared-key sync lag ->
    # "NoneType while decrypting"); the long-running publishers survive it only because
    # they retry every cycle. Re-sending is idempotent — the planner caches by
    # (source, intersection_name), so repeats just refresh the same incident.
    payload = wire.encode(rec)
    frm, to = roles.atsign_for("intxn_market_st"), roles.atsign_for("planner")
    pub = AtPublisher(frm)  # one client, reused across attempts (keeps the shared key warm)
    attempts = int(os.environ.get("INCIDENT_ATTEMPTS", "3"))
    print(f"💥 injecting incident on {shortest} at ({tp['lat']}, {tp['lon']}), density=30")
    print(f"   {frm} -> {to}  (sending {attempts}x to beat first-notification sync lag)")
    for i in range(1, attempts + 1):
        try:
            notify_id = pub.notify(to, "live_traffic", payload)
            print(f"   [{i}/{attempts}] sent (notify id: {notify_id})")
        except Exception as e:
            print(f"   [{i}/{attempts}] send error: {e}")
        if i < attempts:
            time.sleep(3)
    print("   planner reroutes within ~8s of a successful decrypt; clears after ~60s (TTL).")


if __name__ == "__main__":
    main()
