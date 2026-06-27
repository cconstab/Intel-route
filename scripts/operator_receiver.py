#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Headless stand-in for the operator console's data feed (the full console reuses
Intel's Gradio UI — see atsign/operator_console.py). Runs as the operator atSign,
receives the network status the planner pushes.

Run: python scripts/operator_receiver.py
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
    if wire.key_name_from_atkey(key) != "status" or frm != PLANNER:
        return
    d = json.loads(value)
    print("\n🖥️  OPERATOR CONSOLE — network status update")
    print(f"   optimal route : {d['optimal_route']}  ({d['distance_km']:.1f} km)")
    print(f"   agent status  : {d['agent_status']}")
    print(f"   reason        : {d['reason']}")
    print(f"   intersections : {d['intersections']}")


def main():
    me = roles.atsign_for("operator")
    print(f"[operator] {me} waiting for status from {PLANNER} ...")
    AtSubscriber(me, roles.namespace(), on_record).start()


if __name__ == "__main__":
    main()
