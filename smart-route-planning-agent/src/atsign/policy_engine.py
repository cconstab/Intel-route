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
import time

from at_client import AtClient
from at_client.common import AtSign
from at_client.common.keys import SelfKey
from at_client.connections import Address

from atsign import roles
from atsign.atsign_io import AtPublisher

PUBLISHER_ROLES = [
    "intxn_market_st", "intxn_5th_ave", "intxn_broadway",
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
                    help="comma-separated roles to authorize (default: all publishers)")
    ap.add_argument("--interval", type=float, default=8.0)
    ap.add_argument("--repeat", type=int, default=3, help="times to (re)publish the policy")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    me_str = roles.atsign_for("policy")
    me = AtSign(me_str)
    granted_roles = [r.strip() for r in args.grant.split(",") if r.strip()]
    granted = {roles.atsign_for(r) for r in granted_roles}
    denied = {roles.atsign_for(r) for r in PUBLISHER_ROLES} - granted

    print(f"[policy] engine {me_str}; granting {sorted(granted)}")
    if denied:
        print(f"[policy] NOT granting (default-deny): {sorted(denied)}")

    # 1) Persist rules in the engine's own atSign store.
    engine = AtClient(me, root_address=Address.from_string(roles.root()), verbose=args.verbose)
    store = AtKeyPolicyStore(engine, me)
    for s in granted:
        store.grant(s)
    for s in denied:
        store.revoke(s)
    print(f"[policy] rules persisted as atKeys in {me_str}'s store")

    # 2) Publish the authorization set to the planner (re-publish so late joiners get it).
    planner = roles.atsign_for("planner")
    pub = AtPublisher(me_str)
    grants_doc = json.dumps({"grants": sorted(granted), "issued_by": me_str})
    for i in range(args.repeat):
        pub.notify(planner, "policy", grants_doc)
        print(f"[policy] published policy -> {planner} ({i + 1}/{args.repeat})")
        if i < args.repeat - 1:
            time.sleep(args.interval)
    print("[policy] done.")


if __name__ == "__main__":
    main(sys.argv[1:])
