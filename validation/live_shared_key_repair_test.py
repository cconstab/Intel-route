#!/usr/bin/env python3
"""Reproduce the permanent 'Failed to decrypt shared_key ... Ciphertext length must be
equal to key size' wedge by corrupting the sender's stored copy of a shared key,
exactly as a desynchronised write would.

Then check whether publishing can recover.
"""
import sys

sys.path.insert(0, "/Users/cconstab/scratch/Intel-route/smart-route-planning-agent/src")
from atsign.atsign_io import AtPublisher  # noqa: E402

ROOT = "vip.ve.atsign.zone:64"
NS = "smartroute"
ME, TO = "@bravo", "@alpha"


def main():
    pub = AtPublisher(ME, root=ROOT)
    print("1. healthy publish:", flush=True)
    pub.notify(TO, "ck", "HEALTHY", namespace=NS)
    print("   ok", flush=True)

    # Corrupt our own stored copy of the shared key, the record the failing log line
    # names: shared_key.<recipient without @>@<me>
    record = f"shared_key.{TO.lstrip('@')}{ME}"
    print(f"\n2. corrupting {record} (as a desynchronised write would)", flush=True)
    pub.client.secondary_connection.execute_command(
        f"update:{record} bm90LWFuLXJzYS1ibG9i", True)  # valid base64, wrong length
    print("   corrupted", flush=True)

    print("\n3. publish again with the corrupt key:", flush=True)
    try:
        pub.notify(TO, "ck", "AFTER_CORRUPTION", namespace=NS)
        print("   RECOVERED — publishing worked", flush=True)
        return 0
    except Exception as e:
        print(f"   FAILED: {type(e).__name__}: {str(e)[:120]}", flush=True)
        print("\n   >>> matches the reported wedge: it cannot recover on its own,", flush=True)
        print("       and a restart would re-read the same corrupt record.", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
