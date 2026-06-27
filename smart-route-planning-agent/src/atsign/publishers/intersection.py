# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Intersection agent publisher (demo) — stands in for a Smart Traffic Intersection
running Scene Intelligence. Publishes `live_traffic.smartroute` (LiveTrafficData)
to the planner, cycling vehicle density so the planner sees reroute-worthy values.

Run (keys in $HOME/.atsign/keys):
    python -m atsign.publishers.intersection --role intxn_market_st --count 5
"""
import argparse
import sys
import time

from schema import GeoCoordinates, LiveTrafficData
from config import IncidentStatus, WeatherStatus
from atsign import roles, wire
from atsign.atsign_io import AtPublisher

# Demo coordinates per intersection role (placeholder; align to GPX trackpoints later).
INTERSECTIONS = {
    "intxn_market_st": ("Market St & 1st", 37.7946, -122.3999),
    "intxn_5th_ave": ("5th Ave & Mission", 37.7825, -122.4079),
    "intxn_broadway": ("Broadway & Columbus", 37.7980, -122.4070),
}
DENSITIES = [3, 6, 9, 14, 22, 30]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=list(INTERSECTIONS))
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    name, lat, lon = INTERSECTIONS[args.role]
    me = roles.atsign_for(args.role)
    planner = roles.atsign_for("planner")
    pub = AtPublisher(me, verbose=args.verbose)
    print(f"[{args.role}] {me} -> {planner} publishing live_traffic.{roles.namespace()}")

    for i in range(args.count):
        density = DENSITIES[min(i, len(DENSITIES) - 1)]
        rec = LiveTrafficData(
            location_coordinates=GeoCoordinates(latitude=lat, longitude=lon),
            intersection_name=name,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            traffic_density=density,
            traffic_description=f"{name}: density {density}",
            weather_status=WeatherStatus.FLOOD if density > 20 else WeatherStatus.CLEAR,
            incident_status=IncidentStatus.CROWDING if density > 12 else IncidentStatus.CLEAR,
        )
        resp = pub.notify(planner, "live_traffic", wire.encode(rec))
        print(f"[{args.role}] sent #{i + 1}/{args.count} density={density} -> {resp}")
        if i < args.count - 1:
            time.sleep(args.interval)
    print(f"[{args.role}] done.")


if __name__ == "__main__":
    main(sys.argv[1:])
