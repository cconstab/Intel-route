# Copyright (C) 2026 Intel Corporation / Atsign migration spike
# SPDX-License-Identifier: Apache-2.0
"""
Spike subscriber — stands in for the Smart Route Planner (@smartroute_planner).

Subscribes to the `.smartroute` namespace, decrypts incoming LiveTrafficData
notifications, validates them against the wire contract, and maintains an
in-memory cache keyed by intersection name. This is exactly the receive side
the real planner needs: the cache is what the SWAP'd `live_traffic.py`
`fetch_route_status()` will read instead of polling URLs.

Run (needs the planner's .atKeys in ~/.atsign/keys/):

    python subscriber.py --atsign @smartroute_planner --regex smartroute
"""
import argparse
import sys
import threading
from queue import Queue, Empty

from at_client import AtClient
from at_client.common import AtSign
from at_client.common.keys import SharedKey
from at_client.connections import Address
from at_client.connections.notification.atevents import AtEventType

import payload

# The planner's live-traffic cache: intersection_name -> LiveTrafficData dict.
CACHE: dict[str, dict] = {}
_received = 0


def consume(q: Queue, client: AtClient):
    """Drain the monitor queue; decrypt, validate, and cache each record."""
    global _received
    while True:
        try:
            at_event = q.get(block=True, timeout=1.0)
        except Empty:
            continue

        # handle_event decrypts UPDATE_NOTIFICATION -> re-enqueues DECRYPTED_*
        client.handle_event(q, at_event)

        if at_event.event_type != AtEventType.DECRYPTED_UPDATE_NOTIFICATION:
            continue

        data = at_event.event_data
        key = data.get("key", "")
        if payload.__name__ and "smartroute" not in key:
            continue  # not ours

        try:
            record = payload.decode(str(data["decryptedValue"]))
        except Exception as e:
            print(f"[subscriber] FAIL decode: {e}")
            continue

        problems = payload.validate(record)
        if problems:
            print(f"[subscriber] FAIL validate {key}: {problems}")
            continue

        name = record["intersection_name"]
        CACHE[name] = record
        _received += 1
        print(
            f"[subscriber] OK  #{_received}  key={key}\n"
            f"             {name}  density={record['traffic_density']} "
            f"weather={record['weather_status']} incident={record['incident_status']}"
        )
        print(f"[subscriber] cache now holds {len(CACHE)} intersection(s): {list(CACHE)}")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--atsign", required=True, help="Planner atSign, e.g. @smartroute_planner")
    ap.add_argument("--regex", default="smartroute", help="Namespace/regex to monitor")
    ap.add_argument("--root", default="root.atsign.org:64")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    planner = AtSign(args.atsign)
    q: Queue = Queue()

    print(f"[subscriber] connecting as {args.atsign} ...")
    client = AtClient(planner, root_address=Address.from_string(args.root), queue=q, verbose=args.verbose)
    print(f"[subscriber] connected. Monitoring regex '{args.regex}'. Waiting for pushes (Ctrl-C to stop) ...")

    threading.Thread(target=consume, args=(q, client), daemon=True).start()
    # start_monitor blocks; run it on the main thread so Ctrl-C works cleanly.
    try:
        client.start_monitor(args.regex)
    except KeyboardInterrupt:
        print(f"\n[subscriber] stopped. Received {_received} record(s); cache: {list(CACHE)}")


if __name__ == "__main__":
    main(sys.argv[1:])
