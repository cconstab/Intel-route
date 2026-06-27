# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Conditions feed publisher (demo) — weather / traffic-trends / planned-events.

Reads the same bundled CSVs Intel ships (the CSV read moves from the planner to
the data source) and publishes each row as the matching `schema.py` model. Swap a
CSV for a real provider later with no planner change.

Run (keys in $HOME/.atsign/keys):
    python -m atsign.publishers.feed --role weather_feed --count 8
"""
import argparse
import csv
import sys
import time

from config import ROUTE_STATUS_DIR, CongestionLevel, WeatherStatus
from schema import GeoCoordinates, WeatherData, TrafficTrendsData, PlannedEventsData
from atsign import roles, wire
from atsign.atsign_io import AtPublisher


def _coords(row):
    return GeoCoordinates(latitude=float(row["latitude"]), longitude=float(row["longitude"]))


def build_weather(row):
    return WeatherData(
        location_coordinates=_coords(row),
        weather_condition=WeatherStatus(row["condition"]),  # _missing_ -> CLEAR if unknown
        temperature=float(row["temperature"]),
        visibility=float(row["visibility"]),
    )


def build_traffic(row):
    return TrafficTrendsData(
        location_coordinates=_coords(row),
        vehicle_count=int(row["vehicle_count"]),
        avg_speed=int(row["average_speed"]),
        congestion_level=CongestionLevel(row["congestion_level"]),
    )


def build_events(row):
    return PlannedEventsData(
        location_coordinates=_coords(row),
        event_name=row["event_name"],
        congestion_level=CongestionLevel(row["traffic_impact"]),
    )


FEEDS = {
    "weather_feed": ("weather_report.csv", "weather", build_weather),
    "traffic_trends_feed": ("traffic_trends.csv", "traffic_trends", build_traffic),
    "events_feed": ("planned_events.csv", "planned_events", build_events),
}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=list(FEEDS))
    ap.add_argument("--count", type=int, default=0, help="rows to publish (0 = all)")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    csv_name, key_name, build = FEEDS[args.role]
    me = roles.atsign_for(args.role)
    planner = roles.atsign_for("planner")
    pub = AtPublisher(me, verbose=args.verbose)
    print(f"[{args.role}] {me} -> {planner} publishing {key_name}.{roles.namespace()} from {csv_name}")

    with open(ROUTE_STATUS_DIR / csv_name) as f:
        rows = list(csv.DictReader(f))
    if args.count:
        rows = rows[: args.count]

    for i, row in enumerate(rows):
        try:
            model = build(row)
        except Exception as e:
            print(f"[{args.role}] skip row {i}: {e}")
            continue
        resp = pub.notify(planner, key_name, wire.encode(model))
        print(f"[{args.role}] sent #{i + 1}/{len(rows)} -> {resp}")
        time.sleep(args.interval)
    print(f"[{args.role}] done ({len(rows)} rows).")


if __name__ == "__main__":
    main(sys.argv[1:])
