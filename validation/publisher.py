# Copyright (C) 2026 Intel Corporation / Atsign migration spike
# SPDX-License-Identifier: Apache-2.0
"""
Spike publisher — stands in for an intersection agent (e.g. @intxn_market_st).

Pushes LiveTrafficData records to the planner over an encrypted Atsign
notification (the send side of Path B). This is the kernel of the real
intersection/weather/events publishers.

Run (needs the publisher's .atKeys in ~/.atsign/keys/):

    python publisher.py --atsign @intxn_market_st --to @smartroute_planner \\
        --key-name live_traffic --namespace smartroute --count 5 --interval 4
"""
import argparse
import sys
import time
import uuid

from at_client import AtClient
from at_client.common import AtSign
from at_client.connections import Address
from at_client.common.keys import SharedKey
from at_client.util.encryptionutil import EncryptionUtil

import payload


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--atsign", required=True, help="Publisher atSign, e.g. @intxn_market_st")
    ap.add_argument("--to", required=True, help="Subscriber atSign, e.g. @smartroute_planner")
    ap.add_argument("--key-name", default="live_traffic")
    ap.add_argument("--namespace", default="smartroute")
    ap.add_argument("--count", type=int, default=5, help="How many notifications to send")
    ap.add_argument("--interval", type=float, default=4.0, help="Seconds between notifications")
    ap.add_argument("--root", default="root.atsign.org:64")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    publisher = AtSign(args.atsign)
    planner = AtSign(args.to)

    print(f"[publisher] connecting as {args.atsign} ...")
    client = AtClient(publisher, root_address=Address.from_string(args.root), verbose=args.verbose)
    print(f"[publisher] connected. Notifying {args.to} on '{args.key_name}.{args.namespace}'")

    # Simulate congestion building up so the planner sees a reroute-worthy value.
    densities = [3, 6, 9, 14, 22, 30]

    for i in range(args.count):
        density = densities[min(i, len(densities) - 1)]
        record = payload.make_live_traffic(
            intersection_name="Market St & 1st",
            latitude=37.7946,
            longitude=-122.3999,
            traffic_density=density,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            weather_status="Flash Floods" if density > 20 else "Clear",
            incident_status="crowding" if density > 12 else "clear",
            traffic_description=f"density={density}",
        )

        # Build a fresh SharedKey per send (encrypted for the planner).
        sk = SharedKey(args.key_name, publisher, planner)
        sk.set_namespace(args.namespace)
        sk.set_time_to_live(60_000)  # 60s TTL so stale records self-expire
        # Beta-SDK note: notify() reads at_key.metadata.iv_nonce and passes it
        # straight to AES-CTR, so it MUST be set (a None here crashes encryption).
        # The IV travels in the notification metadata; the receiver decrypts with it.
        sk.metadata.iv_nonce = EncryptionUtil.generate_iv_nonce()

        value = payload.encode(record)
        # Beta-SDK note: notify()'s default session_id is a single uuid evaluated
        # once at import, so every notification would share an id and the server
        # dedups them. Pass a fresh id per send.
        resp = client.notify(sk, value, session_id=str(uuid.uuid4()))
        print(f"[publisher] sent #{i + 1}/{args.count} density={density} -> {resp}")
        if i < args.count - 1:
            time.sleep(args.interval)

    print("[publisher] done.")


if __name__ == "__main__":
    main(sys.argv[1:])
