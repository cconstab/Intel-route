#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Onboard every role's ephemeral-environment atSign (from config/ee_atsigns.json)
against the local EE root, generating .atKeys under the current HOME.

Reads each atSign's CRAM secret from the running `atsign-ee` container, then runs
the validated CRAM->PKAM onboarding flow (spike/onboard_ee.py).

Run:
    HOME=/tmp/eehome python scripts/onboard_all_ee.py
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/ — for onboard_ee
import onboard_ee  # noqa: E402

CONTAINER = os.environ.get("EE_CONTAINER", "atsign-ee")


def cram_for(atsign: str) -> str:
    name = atsign.lstrip("@")
    return subprocess.check_output(
        ["docker", "exec", CONTAINER, "cat", f"/atsign/atservers/{name}/CRAM"]
    ).decode().strip()


def main():
    cfg = json.load(open(os.path.join(ROOT, "config", "ee_atsigns.json")))
    root = cfg["rootDomain"]
    ok, failed = [], []
    keys_dir = os.path.expanduser("~/.atsign/keys")
    for role, m in cfg["roles"].items():
        at = m["ee"]
        keyfile = os.path.join(keys_dir, f"{at}_key.atKeys")
        if os.path.exists(keyfile):
            print(f"\n=== {role}: {at} already onboarded (keys present) — skip ===")
            ok.append(f"{role}={at} (existing)")
            continue
        print(f"\n=== {role}: onboarding {at} ===")
        try:
            cram = cram_for(at)
            onboard_ee.main(["-a", at, "-c", cram, "-r", root])
            ok.append(f"{role}={at}")
        except Exception as e:
            print(f"  FAILED {at}: {e}")
            failed.append(f"{role}={at}")
    print(f"\n==== onboarded {len(ok)}/{len(ok) + len(failed)} ====")
    print("OK:    ", ", ".join(ok))
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
