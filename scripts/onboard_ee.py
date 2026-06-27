# Copyright (C) 2026 Intel Corporation / Atsign migration spike
# SPDX-License-Identifier: Apache-2.0
"""
Onboard an atSign via CRAM against a (local ephemeral) root, generating its
.atKeys. Mirrors the SDK's examples/onboarding.py but defaults to the local EE
root. Run under an isolated HOME so EE keys never touch a real keystore:

    HOME=/tmp/eehome PYTHONPATH=/tmp/ee_site:. \\
      python onboard_ee.py -a @alpha -c <CRAM> -r 127.0.0.1.nip.io:64
"""
import sys
from argparse import ArgumentParser

from at_client.connections import Address, AtRootConnection, AtSecondaryConnection
from at_client.common import AtSign
from at_client.util import AuthUtil, OnboardingUtil, KeysUtil


def main(argv):
    ap = ArgumentParser()
    ap.add_argument("-r", "--url", default="127.0.0.1.nip.io:64")
    ap.add_argument("-a", "--atsign", required=True)
    ap.add_argument("-c", "--secret", required=True)
    args = ap.parse_args(argv)

    atsign = AtSign(args.atsign)
    root_address = Address.from_string(args.url)

    print(f"[onboard] find secondary for {args.atsign} via {args.url}")
    secondary = AtRootConnection.get_instance(root_address.host, root_address.port).find_secondary(atsign)
    print(f"[onboard] secondary = {secondary}")

    conn = AtSecondaryConnection(secondary)
    conn.connect()

    auth, ob = AuthUtil(), OnboardingUtil()
    print("[onboard] CRAM auth ...")
    auth.authenticate_with_cram(conn, atsign, args.secret)

    keys = {}
    ob.generate_self_encryption_key(keys)
    ob.generate_pkam_keypair(keys)
    ob.generate_encryption_keypair(keys)
    KeysUtil.save_keys(atsign, keys)

    ob.store_pkam_public_key(conn, keys)
    auth.authenticate_with_pkam(conn, atsign, KeysUtil.load_keys(atsign))
    ob.store_public_encryption_key(conn, atsign.without_prefix, keys)
    ob.delete_cram_key(conn)
    print(f"[onboard] ONBOARDED {args.atsign} ✅")


if __name__ == "__main__":
    main(sys.argv[1:])
