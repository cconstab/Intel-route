#!/usr/bin/env python3
"""
Interop helper using the Python at_python branch (fix/put-get-random-iv).
Put/get self and shared keys against an atServer so a Dart peer can read/write them.

  PYTHONPATH=<at_python> HOME=/tmp/eehome python iv_interop.py \
      --atsign @alpha --op put-shared --key demo --value hi --shared-with @bravo
"""
import argparse

from at_client import AtClient
from at_client.common import AtSign
from at_client.common.keys import SelfKey, SharedKey
from at_client.connections import Address

NS = "itest"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--atsign", required=True)
    ap.add_argument("--op", required=True,
                    choices=["put-self", "get-self", "put-shared", "get-shared"])
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", default="")
    ap.add_argument("--shared-with")
    ap.add_argument("--root", default="vip.ve.atsign.zone:64")
    a = ap.parse_args()

    client = AtClient(AtSign(a.atsign), root_address=Address.from_string(a.root))

    if a.op == "put-self":
        k = SelfKey(a.key, AtSign(a.atsign)); k.set_namespace(NS)
        client.put(k, a.value); print("OK")
    elif a.op == "get-self":
        k = SelfKey(a.key, AtSign(a.atsign)); k.set_namespace(NS)
        print("VALUE:" + client.get(k))
    elif a.op == "put-shared":
        k = SharedKey(a.key, AtSign(a.atsign), AtSign(a.shared_with)); k.set_namespace(NS)
        client.put(k, a.value); print("OK")
    elif a.op == "get-shared":
        # I am the recipient; the record was shared_by --shared-with, shared_with me.
        k = SharedKey(a.key, AtSign(a.shared_with), AtSign(a.atsign)); k.set_namespace(NS)
        print("VALUE:" + client.get(k))


if __name__ == "__main__":
    main()
