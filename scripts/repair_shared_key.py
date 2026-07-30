#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Repair a corrupt shared key between two atSigns.

Symptom in the logs (repeats every cycle, and a restart does NOT clear it):

    [publisher @sender] notify to @recipient failed (Failed to decrypt
    shared_key.recipient@sender - Ciphertext length must be equal to key size.)

The AES key a sender shares with a recipient is stored twice — the sender's own copy
(`shared_key.<recipient>@<sender>`) and the recipient's (`@<recipient>:shared_key@<sender>`).
If the sender's copy becomes unreadable, every later send to that recipient fails the
same way forever, because the bad record is re-read each time. Deleting both copies
makes the SDK mint a fresh pair on the next send.

Run as the SENDER (the atSign named after the '@' in the record):

    ATSIGN_PROFILE=vanity PYTHONPATH=$PWD/smart-route-planning-agent/src \\
      python scripts/repair_shared_key.py --role planner --to-role operator

    # or with explicit atSigns
    python scripts/repair_shared_key.py --atsign @sender --to @recipient
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from atsign import roles  # noqa: E402
from atsign.atsign_io import AtPublisher  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--atsign", help="the SENDER atSign (or use --role)")
    ap.add_argument("--to", help="the RECIPIENT atSign (or use --to-role)")
    ap.add_argument("--role", help="sender by role, e.g. planner")
    ap.add_argument("--to-role", help="recipient by role, e.g. operator")
    args = ap.parse_args()

    sender = args.atsign or (roles.atsign_for(args.role) if args.role else None)
    recipient = args.to or (roles.atsign_for(args.to_role) if args.to_role else None)
    if not sender or not recipient:
        ap.error("need a sender (--atsign/--role) and a recipient (--to/--to-role)")

    print(f"repairing the shared key {sender} -> {recipient} "
          f"(profile={os.environ.get('ATSIGN_PROFILE', 'ee')})")
    pub = AtPublisher(sender)
    if not pub._repair_shared_key(recipient):
        print("nothing was deleted — check the atSigns and that this host holds "
              "the sender's .atKeys")
        return 1

    # Prove it: this send has to create a fresh key pair and succeed.
    print("verifying with a test notification...")
    try:
        pub.notify(recipient, "repair_check", "shared key repaired")
        print("OK — a fresh shared key was created and the send succeeded.")
        return 0
    except Exception as e:
        print(f"still failing: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
