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
        path = os.environ.get("ATSIGN_CONFIG")
        if not path:
            here = os.path.dirname(os.path.abspath(__file__))
            path = os.path.normpath(os.path.join(here, "..", "..", "..", "config", "ee_atsigns.json"))
        with open(path) as f:
            _CFG = json.load(f)
    return _CFG


def _profile() -> str:
    return os.environ.get("ATSIGN_PROFILE", "ee")  # "ee" (default) or "vanity"


def atsign_for(role: str) -> str:
    return _load()["roles"][role][_profile()]


def publisher_roles() -> list:
    """Roles that publish into the planner: intersections and data feeds.

    Read from the config, because the policy engine and the Dart policy admin must agree
    on which publishers exist. The admin offers a switch for every `intxn_*` / `*_feed`
    role it finds here, and the engine authorizes only publishers it knows — so a list
    hardcoded in the engine means a publisher added to the config gets a switch that is
    silently dropped on every grant (and, confusingly, works fine on revoke).
    """
    return sorted(r for r in _load()["roles"]
                  if r.startswith("intxn_") or r.endswith("_feed"))


def role_for_atsign(atsign: str) -> str:
    prof = _profile()
    for role, m in _load()["roles"].items():
        if m[prof] == atsign:
            return role
    return "unknown"


def namespace() -> str:
    return _load()["namespace"]


def root() -> str:
    """Root server for the active profile: ee -> local EE, vanity -> production."""
    cfg = _load()
    by_profile = cfg.get("rootDomains", {})
    return by_profile.get(_profile()) or cfg.get("rootDomain") or "root.atsign.org:64"
