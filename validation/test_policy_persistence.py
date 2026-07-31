#!/usr/bin/env python3
"""
Network-free check that a revocation survives a restart.

The engine used to start from --grant every time, which meant "all publishers granted",
and it never read back the rules it wrote. Restarting the engine therefore re-authorised
a publisher the operator had revoked. The engine's own rule records are the source of
truth; --grant only seeds an atSign that has never held rules.

Run: PYTHONPATH=smart-route-planning-agent/src python validation/test_policy_persistence.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))

from at_client.exception.atexception import AtKeyNotFoundException  # noqa: E402
from at_client.util.verbbuilder import ScanVerbBuilder  # noqa: E402

from at_client.exception.atexception import AtInvalidSyntaxException  # noqa: E402

from atsign import roles  # noqa: E402
from atsign.policy_engine import AtKeyPolicyStore, initial_grants  # noqa: E402

PUBLISHERS = {"@intxn_market_st", "@intxn_5th_ave", "@weather_feed"}


class FakeReply:
    def __init__(self, raw):
        self._raw = raw

    def get_raw_data_response(self):
        return self._raw


class FakeConnection:
    """Answers scan the way a secondary does: full key strings, owner atSign included.

    The command is validated against what the SDK's own builder produces. An earlier
    version of this fake accepted a hand-built "scan:rule." — which a real server rejects
    with AT0003 Invalid syntax, because the regex follows a space — so the test passed
    while the engine could not start at all.
    """

    def __init__(self, records, owner):
        self.records = records
        self.owner = owner

    def execute_command(self, command, _raise=True):
        expected = ScanVerbBuilder().set_regex("rule.").build()
        if command != expected:
            raise AtInvalidSyntaxException(
                f"AT0003-Invalid syntax : Invalid syntax. {command}")
        pattern = command.split(" ", 1)[1]
        matched = [name if "@" in name else f"{name}@{self.owner.lstrip('@')}"
                   for name in self.records if pattern in name]
        return FakeReply(str(matched).replace("'", '"'))


class FakeClient:
    """An in-memory atSign store, with the same failure it reports for a missing key."""

    def __init__(self, owner="@route_policy"):
        self.records = {}
        self.secondary_connection = FakeConnection(self.records, owner)
        self.readable = True

    def _name(self, key):
        return f"{key.name}.{roles.namespace()}"

    def put(self, key, value):
        self.records[self._name(key)] = value

    def get(self, key):
        if not self.readable:
            raise RuntimeError("connection reset by peer")
        name = self._name(key)
        if name not in self.records:
            raise AtKeyNotFoundException(f"{name} does not exist")
        return self.records[name]

    def delete(self, key):
        self.records.pop(self._name(key), None)


def store_for(client):
    return AtKeyPolicyStore(client, client.secondary_connection.owner)


def persist(store, granted):
    """What the engine does on every rule change."""
    for subject in PUBLISHERS:
        (store.grant if subject in granted else store.revoke)(subject)


def main():
    # 1. An atSign that has never held rules starts from --grant.
    client = FakeClient()
    store = store_for(client)
    seed = set(PUBLISHERS)
    grants, from_store = initial_grants(store, seed, PUBLISHERS)
    assert (grants, from_store) == (seed, False), (grants, from_store)
    print("first run          -> seeds from --grant")

    # 2. Once written, the store is what the engine reads back.
    persist(store, seed)
    store.mark_initialised()
    grants, from_store = initial_grants(store, seed, PUBLISHERS)
    assert (grants, from_store) == (seed, True), (grants, from_store)
    print("after persisting   -> reads its own rules back")

    # 3. The reported bug: revoke, restart, and the revocation must hold. --grant still
    #    names every publisher, exactly as start_stack.sh passes it.
    revoked = seed - {"@intxn_market_st"}
    persist(store, revoked)
    grants, from_store = initial_grants(store, seed, PUBLISHERS)
    assert grants == revoked, f"restart re-granted a revoked publisher: {grants}"
    assert from_store
    print("revoke + restart   -> @intxn_market_st stays revoked")

    # 4. Revoking everything is a real state, not an empty store to be re-seeded.
    persist(store, set())
    grants, from_store = initial_grants(store, seed, PUBLISHERS)
    assert (grants, from_store) == (set(), True), (grants, from_store)
    print("everything revoked -> stays revoked, not re-seeded")

    # 5. Re-granting works the same way round.
    persist(store, {"@weather_feed"})
    grants, _ = initial_grants(store, seed, PUBLISHERS)
    assert grants == {"@weather_feed"}, grants
    print("re-grant one       -> only that publisher is authorized")

    # 6. An unreadable store must raise, not look like a first run: the caller refuses to
    #    start rather than fall back to --grant and re-authorise everyone.
    client.readable = False
    try:
        initial_grants(store, seed, PUBLISHERS)
        raise AssertionError("an unreadable store was treated as a first run")
    except RuntimeError:
        pass
    print("unreadable store   -> raises instead of granting everything")

    # 7. Only the engine's own rule records count. A key another atSign shares with the
    #    engine appears in its scan too, and must never become a grant.
    client.readable = True
    client.records["route.smartroute"] = "not a rule"
    client.records["policy_initialised.smartroute"] = "1"
    for hostile in ("@route_policy:rule.attacker.smartroute@attacker",
                    "cached:@route_policy:rule.attacker.smartroute@attacker",
                    "public:rule.attacker.smartroute@attacker"):
        client.records[hostile] = "allow"
    grants, _ = initial_grants(store, seed, PUBLISHERS)
    assert grants == {"@weather_feed"}, grants
    print("unrelated records  -> ignored, including rules shared BY another atSign")

    # 8. A publisher retired from the config cannot linger in the authorized set.
    store.grant("@decommissioned_feed")
    grants, _ = initial_grants(store, seed, PUBLISHERS)
    assert grants == {"@weather_feed"}, grants
    print("unknown subject    -> dropped, not authorized")

    # 9. The scan command must be the SDK's, not a hand-built string. A real server
    #    answers AT0003 Invalid syntax otherwise, and the engine then refuses to start.
    assert ScanVerbBuilder().set_regex("rule.").build() == "scan rule.", "scan syntax moved"
    try:
        client.secondary_connection.execute_command("scan:rule.", True)
        raise AssertionError("a hand-built 'scan:rule.' must be rejected, as a server does")
    except AtInvalidSyntaxException:
        pass
    print("scan command       -> built by the SDK; a hand-built one is rejected")

    # 10. The engine must authorize whatever the config calls a publisher. The admin
    #     offers a switch for every intxn_* / *_feed role it finds there, and the engine
    #     drops anything it does not know — silently, and only on grant, because a revoke
    #     of an unknown atSign looks identical to success. A hardcoded list in the engine
    #     therefore produces a switch that can never be turned on.
    import json
    import tempfile

    original_cfg = roles._CFG
    original_path = os.environ.get("ATSIGN_CONFIG")
    try:
        config = json.loads(json.dumps(roles._load()))  # deep copy
        config["roles"]["intxn_phone"] = {"ee": "@phone_ee", "vanity": "@phone_vanity"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            temp_path = f.name
        os.environ["ATSIGN_CONFIG"] = temp_path
        roles._CFG = None
        assert "intxn_phone" in roles.publisher_roles(), (
            "a publisher added to the config is not authorizable — the engine is not "
            "reading the config")
    finally:
        roles._CFG = original_cfg
        if original_path is None:
            os.environ.pop("ATSIGN_CONFIG", None)
        else:
            os.environ["ATSIGN_CONFIG"] = original_path
        os.unlink(temp_path)
    print("new publisher      -> authorizable without editing the engine")

    print("\nPASS: rules are read back from the store, so revocations survive a restart.")


if __name__ == "__main__":
    main()
