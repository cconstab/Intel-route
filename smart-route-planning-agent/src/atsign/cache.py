# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
In-memory cache the planner's subscriber fills from inbound notifications and the
SWAP'd controllers read. Replaces Intel's request/poll + CSV reads: the same
`schema.py` models the graph already understands, now sourced from pushed records.
Thread-safe.
"""
import threading
from typing import List, Optional

from schema import LiveTrafficData

_lock = threading.RLock()

# Live traffic: (source_atsign, intersection_name) -> latest LiveTrafficData
_live_traffic: dict = {}

# Conditions, by kind ("weather" | "traffic_trends" | "planned_events"):
#   kind -> { (source_atsign, lat, lon) -> model }
_conditions: dict = {"weather": {}, "traffic_trends": {}, "planned_events": {}}


# ---- live traffic ----------------------------------------------------------
def put_live_traffic(source: str, model: LiveTrafficData) -> None:
    with _lock:
        _live_traffic[(source, model.intersection_name)] = model


def get_live_traffic() -> List[LiveTrafficData]:
    with _lock:
        return list(_live_traffic.values())


# ---- conditions (weather / traffic trends / planned events) ----------------
def put_condition(kind: str, source: str, model) -> None:
    loc = model.location_coordinates
    with _lock:
        _conditions[kind][(source, loc.latitude, loc.longitude)] = model


def find_condition(kind: str, latitude: float, longitude: float, proximity: float) -> Optional[object]:
    """Return a cached condition near (lat, lon) within `proximity`, or None.

    Mirrors the coordinate matching the original CSV-reading controllers did —
    only the data source changed (pushed records instead of a local CSV).
    """
    with _lock:
        for m in _conditions[kind].values():
            loc = m.location_coordinates
            if abs(loc.latitude - latitude) <= proximity and abs(loc.longitude - longitude) <= proximity:
                return m
    return None


# ---- introspection ---------------------------------------------------------
def size() -> int:
    with _lock:
        return len(_live_traffic)


def conditions_size(kind: str) -> int:
    with _lock:
        return len(_conditions[kind])


def clear() -> None:
    with _lock:
        _live_traffic.clear()
        for k in _conditions:
            _conditions[k].clear()
