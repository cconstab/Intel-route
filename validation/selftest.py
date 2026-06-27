# Copyright (C) 2026 Intel Corporation / Atsign migration spike
# SPDX-License-Identifier: Apache-2.0
"""
Offline self-test — validates the spike codepath WITHOUT atKeys or network.

It cannot prove the live round-trip (that needs two onboarded atSigns), but it
proves everything else is correct: the SDK API we rely on exists with the right
signatures, SharedKey + namespace produce the expected key name, the payload
round-trips, and validation catches malformed records. Green here means the
only remaining unknown is the live network behaviour of the Beta SDK.
"""
import inspect

import payload


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    return cond


def main():
    ok = True
    print("1) SDK API surface")
    from at_client import AtClient
    from at_client.common import AtSign
    from at_client.common.keys import SharedKey
    from at_client.connections.notification.atevents import AtEventType

    ok &= check("AtClient.notify(at_key, value, ...)", "value" in inspect.signature(AtClient.notify).parameters)
    ok &= check("AtClient.start_monitor(regex)", "regex" in inspect.signature(AtClient.start_monitor).parameters)
    ok &= check("AtClient.handle_event exists", hasattr(AtClient, "handle_event"))
    ok &= check("AtClient accepts queue= kwarg", "queue" in inspect.signature(AtClient.__init__).parameters)
    ok &= check("DECRYPTED_UPDATE_NOTIFICATION event type", hasattr(AtEventType, "DECRYPTED_UPDATE_NOTIFICATION"))

    print("2) SharedKey + namespace -> key name")
    pub, planner = AtSign("@intxn_market_st"), AtSign("@smartroute_planner")
    sk = SharedKey("live_traffic", pub, planner)
    sk.set_namespace("smartroute")
    fq = sk.get_fully_qualified_key_name()
    print(f"      fully-qualified key name = {fq!r}")
    ok &= check("key name carries 'live_traffic'", "live_traffic" in fq)
    ok &= check("key name carries namespace 'smartroute'", "smartroute" in fq)
    rendered = str(sk)
    print(f"      str(SharedKey) = {rendered!r}")
    ok &= check("rendered key is monitor-matchable by regex 'smartroute'", "smartroute" in rendered)

    print("3) Payload round-trip (LiveTrafficData shape)")
    rec = payload.make_live_traffic(
        "Market St & 1st", 37.7946, -122.3999, 22,
        "2026-06-26T12:00:00", weather_status="Flash Floods", incident_status="crowding",
        traffic_description="density=22",
    )
    wire = payload.encode(rec)
    back = payload.decode(wire)
    ok &= check("encode->decode is lossless", back == rec)
    ok &= check("well-formed record passes validate()", payload.validate(rec) == [])
    ok &= check("missing-field record fails validate()", payload.validate({"intersection_name": "x"}) != [])
    ok &= check("planner can read coords", back["location_coordinates"]["latitude"] == 37.7946)

    print()
    print("RESULT:", "ALL OFFLINE CHECKS PASSED ✅" if ok else "SOME CHECKS FAILED ❌")
    print("Next: run subscriber.py + publisher.py with two real atSigns for the live round-trip.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
