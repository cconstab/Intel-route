#!/usr/bin/env python3
# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Debug subscriber — runs as the planner atSign, subscribes to the whole `smartroute`
namespace, decodes every record back into its schema model, and prints it labelled
by source role. Used to verify all publishers fan in correctly.

Run (keys in $HOME/.atsign/keys, src on PYTHONPATH):
    python scripts/debug_subscriber.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from atsign import roles, wire           # noqa: E402
from atsign.atsign_io import AtSubscriber  # noqa: E402

_count = 0


def on_record(from_atsign: str, key: str, value: str, raw: dict):
    global _count
    _count += 1
    role = roles.role_for_atsign(from_atsign)
    key_name = wire.key_name_from_atkey(key)
    try:
        model = wire.decode(key_name, value)
        summary = model.model_dump()
    except Exception as e:
        summary = f"<decode error: {e}> raw={value[:80]}"
    print(f"\n#{_count}  {key_name}  from {role} ({from_atsign})")
    print(f"        {summary}")


def main():
    me = roles.atsign_for("planner")
    print(f"[debug-sub] planner {me} monitoring '{roles.namespace()}' — waiting for publishers...")
    AtSubscriber(me, roles.namespace(), on_record).start()


if __name__ == "__main__":
    main()
