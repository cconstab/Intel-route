# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Policy engine (runs as the policy atSign, e.g. @route_policy / EE @juliet).

The zero-trust trust plane. Rules are stored as encrypted records (atKeys) in the
engine's OWN atSign store (the `PolicyStore`), then the engine publishes the
resulting authorization set to the planner. Default-deny: a publisher the engine
has not granted is dropped by the planner.

`PolicyStore` is an interface; `AtKeyPolicyStore` (default) keeps rules as self
atKeys. A database-backed store can be dropped in later (NoPorts-style) with no
change to callers.

Run (as the policy atSign):
    python -m atsign.policy_engine --grant intxn_market_st,intxn_5th_ave,weather_feed,traffic_trends_feed,events_feed
    # (omit a role to demonstrate default-deny — e.g. leave out intxn_broadway)
"""
import argparse
import json
import sys
import threading
import time

from at_client import AtClient
from at_client.common import AtSign
from at_client.common.keys import SelfKey
from at_client.connections import Address

from atsign import roles, wire
from atsign.atsign_io import AtPublisher, AtSubscriber

PUBLISHER_ROLES = [
    "intxn_market_st", "intxn_5th_ave", "intxn_broadway", "intxn_downtown",
    "weather_feed", "traffic_trends_feed", "events_feed",
]


class AtKeyPolicyStore:
    """PolicyStore backed by the engine's own atSign store (rules = self atKeys)."""

    def __init__(self, client: AtClient, me: AtSign):
        self.client = client
        self.me = me

    def _key(self, subject: str) -> SelfKey:
        sk = SelfKey(f"rule.{subject.lstrip('@')}", self.me)
        sk.set_namespace(roles.namespace())
        return sk

    def grant(self, subject: str):
        try:
            self.client.put(self._key(subject), "allow")
        except Exception as e:
            print(f"  (store) could not persist grant for {subject}: {e}")

    def revoke(self, subject: str):
        try:
            self.client.delete(self._key(subject))
        except Exception:
            pass


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--grant", default=",".join(PUBLISHER_ROLES),
                    help="comma-separated roles to authorize initially (default: all publishers)")
    ap.add_argument("--interval", type=float, default=30.0, help="policy re-publish heartbeat (s)")
    ap.add_argument("--repeat", type=int, default=0, help="(accepted for compatibility; ignored — runs as a service)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    me_str = roles.atsign_for("policy")
    me = AtSign(me_str)
    planner = roles.atsign_for("planner")
    admin_atsign = roles.atsign_for("policy_admin")
    all_publishers = {roles.atsign_for(r) for r in PUBLISHER_ROLES}
    granted = {roles.atsign_for(r) for r in args.grant.split(",") if r.strip()}

    engine = AtClient(me, root_address=Address.from_string(roles.root()), verbose=args.verbose)
    store = AtKeyPolicyStore(engine, me)
    pub = AtPublisher(me_str)

    def persist():
        for s in all_publishers:
            (store.grant if s in granted else store.revoke)(s)

    def publish():
        pub.notify(planner, "policy",
                   json.dumps({"grants": sorted(granted), "issued_by": me_str}))

    last_ver = [0]  # ignore stale/replayed admin notifications (monotonic version guard)

    def on_admin(frm, key, value, raw):
        # Only accept rule changes from the authorised Policy Admin atSign (@route_policy_admin).
        if wire.key_name_from_atkey(key) != "admin" or frm != admin_atsign:
            if wire.key_name_from_atkey(key) == "admin":
                print(f"[policy] IGNORED admin change from non-admin {frm}")
            return
        try:
            data = json.loads(value)
            ver = int(data.get("version", 0))
            new_grants = {str(g) for g in data.get("grants", [])}
        except Exception as e:
            print(f"[policy] bad admin payload: {e}")
            return
        if ver <= last_ver[0]:
            return  # stale or replayed — already have a newer rule set
        last_ver[0] = ver
        granted.clear()
        granted.update(new_grants & all_publishers)  # only known publishers
        persist()
        publish()
        print(f"[policy] admin {frm} updated grants -> {sorted(granted)}")

    print(f"[policy] engine {me_str}; initial grants {sorted(granted)}")
    persist()
    publish()
    print(f"[policy] rules persisted as atKeys; published to {planner}")

    # Listen for admin rule changes from @route_policy_admin (segregation of duties).
    time.sleep(2)  # let the engine/publisher connections settle before a 3rd client
    threading.Thread(
        target=lambda: AtSubscriber(me_str, roles.namespace(), on_admin).start(),
        daemon=True,
    ).start()
    print(f"[policy] listening for admin changes from {admin_atsign}; heartbeat every {args.interval}s")

    while True:
        time.sleep(args.interval)
        publish()


if __name__ == "__main__":
    main(sys.argv[1:])
