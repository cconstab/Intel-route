#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Headless stand-in for the Flutter commuter app (the real one is Dart/Flutter;
interop already proven). Runs as the commuter atSign, receives pushed routes and
reroute alerts from the planner.

Run: python scripts/commuter_receiver.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from atsign import roles, wire             # noqa: E402
from atsign.atsign_io import AtSubscriber  # noqa: E402

PLANNER = roles.atsign_for("planner")


def on_record(frm, key, value, raw):
    if wire.key_name_from_atkey(key) != "route" or frm != PLANNER:
        return
    d = json.loads(value)
    if d.get("rerouted"):
        print("\n🚨 REROUTE ALERT (commuter phone)")
    else:
        print("\n🧭 Route received (commuter phone)")
    print(f"   route   : {d['route_name']}  ({d['distance_km']:.1f} km)")
    print(f"   reason  : {d['reason']}")
    print(f"   map pts : {len(d['points'])} points (first {d['points'][:1]})")


def main():
    me = roles.atsign_for("commuter01")
    print(f"[commuter] {me} waiting for pushed routes from {PLANNER} ...")
    AtSubscriber(me, roles.namespace(), on_record).start()


if __name__ == "__main__":
    main()
