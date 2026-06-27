#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Planner-side subscriber (runs as the planner atSign).

- Subscribes to the whole `smartroute` namespace.
- Learns the authorization set from `policy` records (only from the policy atSign).
- Enforces **default-deny**: data records from non-authorized atSigns are dropped.
- Caches authorized `live_traffic` records; the SWAP'd `LiveTrafficController` reads
  that same cache — proving the Intel graph now runs on pushed data, no polling.

Run (keys in $HOME/.atsign/keys):
    python scripts/planner_subscriber.py
"""
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from atsign import roles, wire, cache              # noqa: E402
from atsign.atsign_io import AtSubscriber          # noqa: E402
from controllers.live_traffic import LiveTrafficController  # noqa: E402  (the SWAP'd controller)

POLICY_SOURCE = roles.atsign_for("policy")
ALLOW: set = set()        # authorized publisher atSigns (default-deny: empty = nobody)


def on_record(frm: str, key: str, value: str, raw: dict):
    kn = wire.key_name_from_atkey(key)

    if kn == "policy":
        if frm != POLICY_SOURCE:
            print(f"[planner] IGNORED policy from non-policy atSign {frm}")
            return
        grants = json.loads(value).get("grants", [])
        ALLOW.clear()
        ALLOW.update(grants)
        print(f"[planner] POLICY updated by {frm}: authorized = {sorted(ALLOW)}")
        return

    # data record — enforce default-deny
    if frm not in ALLOW:
        print(f"[planner] DENIED  {kn} from {roles.role_for_atsign(frm)} ({frm}) — not authorized")
        return

    if kn == "live_traffic":
        model = wire.decode(kn, value)
        cache.put_live_traffic(frm, model)
        print(f"[planner] CACHED  live_traffic from {roles.role_for_atsign(frm)}: "
              f"{model.intersection_name} density={model.traffic_density} (cache={cache.size()})")
    elif kn in ("weather", "traffic_trends", "planned_events"):
        model = wire.decode(kn, value)
        cache.put_condition(kn, frm, model)
        print(f"[planner] CACHED  {kn} from {roles.role_for_atsign(frm)} "
              f"(cache[{kn}]={cache.conditions_size(kn)})")
    else:
        print(f"[planner] ACCEPT  {kn} from {roles.role_for_atsign(frm)}")


def _controller_view():
    """Every 6s, read live traffic via the SWAP'd Intel controller (reads the cache)."""
    ctrl = LiveTrafficController()
    while True:
        time.sleep(6)
        records = ctrl.fetch_route_status()
        names = [r.intersection_name for r in records]
        print(f"[planner] LiveTrafficController.fetch_route_status() -> {len(records)}: {names}")


def main():
    me = roles.atsign_for("planner")
    print(f"[planner] {me} subscribing to '{roles.namespace()}'. Default-deny until policy arrives.")
    threading.Thread(target=_controller_view, daemon=True).start()
    AtSubscriber(me, roles.namespace(), on_record).start()


if __name__ == "__main__":
    main()
