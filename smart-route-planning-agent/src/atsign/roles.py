# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Resolve roles -> atSigns from config/ee_atsigns.json (repo root).

Lets code address participants by role ("planner", "weather_feed", ...) and flip
the whole system from ephemeral-environment atSigns to production vanity atSigns
by editing one file. Set ATSIGN_PROFILE=vanity to use the production atSigns.
"""
import json
import os

_CFG = None


def _load():
    global _CFG
    if _CFG is None:
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.normpath(os.path.join(here, "..", "..", "..", "config", "ee_atsigns.json"))
        with open(path) as f:
            _CFG = json.load(f)
    return _CFG


def _profile() -> str:
    return os.environ.get("ATSIGN_PROFILE", "ee")  # "ee" (default) or "vanity"


def atsign_for(role: str) -> str:
    return _load()["roles"][role][_profile()]


def role_for_atsign(atsign: str) -> str:
    prof = _profile()
    for role, m in _load()["roles"].items():
        if m[prof] == atsign:
            return role
    return "unknown"


def namespace() -> str:
    return _load()["namespace"]


def root() -> str:
    return _load()["rootDomain"]
