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
from at_client.exception.atexception import AtKeyNotFoundException

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

    # Written once so an empty rule set ("everything revoked") is distinguishable from
    # a store that has never been written.
    _MARKER = "policy_initialised"

    def _self_key(self, name: str) -> SelfKey:
        sk = SelfKey(name, self.me)
        sk.set_namespace(roles.namespace())
        return sk

    def _key(self, subject: str) -> SelfKey:
        return self._self_key(f"rule.{subject.lstrip('@')}")

    def is_initialised(self) -> bool:
        """Whether rules have ever been written.

        Only a missing marker means "no": any other failure is reported to the caller,
        because "the store cannot be read" must not be treated as "first run", which
        would re-grant every publisher.
        """
        try:
            self.client.get(self._self_key(self._MARKER))
            return True
        except AtKeyNotFoundException:
            return False

    def mark_initialised(self):
        # Deliberately not swallowed: an unmarked store looks like a first run on the
        # next restart, which would re-grant every publisher.
        self.client.put(self._self_key(self._MARKER), "1")

    def load(self) -> set:
        """The subjects holding an allow rule. Presence is the grant; revoke deletes."""
        subjects = set()
        response = self.client.secondary_connection.execute_command("scan:rule.", True)
        for entry in json.loads(response.get_raw_data_response() or "[]"):
            # Only the engine's OWN records count. Anything another atSign shared with us
            # is scanned as "@me:rule.x@them" or "cached:@me:...", so taking the text
            # before the first '@' and requiring a bare "rule." prefix rejects it: a
            # third party must not be able to inject a rule by sharing a key.
            name = str(entry).split("@", 1)[0]
            if not name.startswith("rule."):
                continue
            subject = name[len("rule."):]
            suffix = "." + roles.namespace()
            if subject.endswith(suffix):
                subject = subject[:-len(suffix)]
            if subject:
                subjects.add("@" + subject)
        return subjects

    def grant(self, subject: str):
        self.client.put(self._key(subject), "allow")

    def revoke(self, subject: str):
        try:
            self.client.delete(self._key(subject))
        except AtKeyNotFoundException:
            pass  # never granted, so nothing to remove


def initial_grants(store, seed, known):
    """The rule set an engine should start from: `(grants, came_from_the_store)`.

    Persisted rules always win, including an empty set — "everything revoked" is a real
    state and has to survive a restart. `seed` (--grant) applies only to an atSign that
    has never held rules. Errors are not caught here: an unreadable store must never be
    mistaken for a first run, which would re-authorise every publisher.
    """
    if store.is_initialised():
        return store.load() & set(known), True
    return set(seed), False


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

    # The engine's own rule records are the source of truth: a revocation has to survive
    # a restart. --grant seeds the first run only, because an empty rule set is itself a
    # valid state (everything revoked) and must not be mistaken for an unwritten store.
    try:
        loaded, from_store = initial_grants(store, granted, all_publishers)
    except Exception as e:
        # Refusing to start is the safe outcome: guessing from --grant would silently
        # re-authorise publishers the operator revoked. The planner keeps enforcing the
        # last rule set it was given, so default-deny still holds while this is fixed.
        print(f"[policy] FATAL: the persisted rules could not be read: {e}")
        print("[policy] refusing to start rather than fall back to --grant")
        raise SystemExit(2)
    granted.clear()
    granted.update(loaded)
    print(f"[policy] loaded persisted rules -> {sorted(granted)}" if from_store
          else "[policy] first run on this atSign: seeding rules from --grant")

    def persist():
        failed = []
        for s in all_publishers:
            try:
                (store.grant if s in granted else store.revoke)(s)
            except Exception as e:
                failed.append(f"{s} ({e})")
        if failed:
            print("[policy] WARNING: rules were not fully persisted, so a restart may "
                  f"not reflect this change: {', '.join(failed)}")

    mirror_failed = [False]  # so a heartbeat that cannot reach the admin logs once, not forever

    def publish():
        payload = json.dumps({"grants": sorted(granted), "issued_by": me_str})
        pub.notify(planner, "policy", payload)
        # The admin console renders what the engine actually holds rather than assuming.
        try:
            pub.notify(admin_atsign, "policy", payload)
            if mirror_failed[0]:
                print(f"[policy] rules are reaching {admin_atsign} again")
                mirror_failed[0] = False
        except Exception as e:
            if not mirror_failed[0]:
                print(f"[policy] could not mirror rules to {admin_atsign}, so its page "
                      f"will not update: {e}")
                mirror_failed[0] = True

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
    store.mark_initialised()
    publish()
    print(f"[policy] rules persisted as atKeys; published to {planner} and {admin_atsign}")

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
