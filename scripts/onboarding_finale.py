#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Phase 9 finale — policy-gated DYNAMIC ONBOARDING (single process for orchestration).

A brand-new intersection (`intxn_downtown` / EE @lima) powers on:
  1. It publishes live traffic -> the planner DENIES it (default-deny; not in policy).
  2. The Policy Admin authorizes it (engine republishes the grant set).
  3. It publishes again -> the planner now CACHES it. It joined the live network with
     NO planner restart and NO config edit.

Run:  python scripts/onboarding_finale.py
"""
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from config import WeatherStatus, IncidentStatus  # noqa: E402
from schema import GeoCoordinates, LiveTrafficData  # noqa: E402
from atsign import roles, wire, cache  # noqa: E402
from atsign.atsign_io import AtPublisher, AtSubscriber  # noqa: E402

PLANNER = roles.atsign_for("planner")
POLICY = roles.atsign_for("policy")
NEW = roles.atsign_for("intxn_downtown")
ESTABLISHED = [roles.atsign_for(r) for r in ("intxn_market_st", "intxn_5th_ave", "intxn_broadway")]

ALLOW: set = set()
denied: list = []
cached: list = []


def on_record(frm, key, value, raw):
    kn = wire.key_name_from_atkey(key)
    if kn == "policy":
        if frm == POLICY:
            ALLOW.clear()
            ALLOW.update(json.loads(value).get("grants", []))
            print(f"   [planner] policy now authorizes: {sorted(roles.role_for_atsign(a) for a in ALLOW)}")
        return
    if frm not in ALLOW:
        denied.append(frm)
        print(f"   [planner] ⛔ DENIED {kn} from {roles.role_for_atsign(frm)} ({frm})")
        return
    if kn == "live_traffic":
        cache.put_live_traffic(frm, wire.decode(kn, value))
        cached.append(frm)
        print(f"   [planner] ✅ CACHED live_traffic from {roles.role_for_atsign(frm)} ({frm})")


def publish_downtown():
    rec = LiveTrafficData(
        location_coordinates=GeoCoordinates(latitude=37.3382, longitude=-121.8863),
        intersection_name="Downtown & 2nd",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        traffic_density=8, traffic_description="new intersection online",
        weather_status=WeatherStatus.CLEAR, incident_status=IncidentStatus.CLEAR,
    )
    AtPublisher(NEW).notify(PLANNER, "live_traffic", wire.encode(rec))


def publish_policy(grants):
    AtPublisher(POLICY).notify(PLANNER, "policy", json.dumps({"grants": grants, "issued_by": POLICY}))


def wait(pred, t=20):
    for _ in range(t * 2):
        if pred():
            return True
        time.sleep(0.5)
    return False


def main():
    print(f"[finale] planner {PLANNER} subscribing; new intersection = intxn_downtown ({NEW})")
    threading.Thread(target=lambda: AtSubscriber(PLANNER, roles.namespace(), on_record).start(), daemon=True).start()
    time.sleep(3)

    print("\n— Step 0: policy grants only the established intersections —")
    publish_policy(ESTABLISHED)
    wait(lambda: ALLOW == set(ESTABLISHED))

    print("\n— Step 1: the NEW intersection powers on and publishes (expect DENIED) —")
    cached.clear()
    publish_downtown()
    wait(lambda: NEW in denied)
    step1 = NEW not in cached

    print("\n— Step 2: Policy Admin authorizes the new intersection —")
    publish_policy(ESTABLISHED + [NEW])
    wait(lambda: NEW in ALLOW)

    print("\n— Step 3: the new intersection publishes again (expect CACHED, no restart) —")
    publish_downtown()
    wait(lambda: NEW in cached)
    names = [m.intersection_name for m in cache.get_live_traffic()]

    print("\n==================== RESULT ====================")
    print(f"  before authorization : DENIED (default-deny) = {step1}")
    print(f"  after authorization  : joined live = {NEW in cached}")
    print(f"  planner live cache now includes: {names}")
    print("  → a new intersection joined the running network with no restart, no config edit.")
    os._exit(0)


if __name__ == "__main__":
    main()
