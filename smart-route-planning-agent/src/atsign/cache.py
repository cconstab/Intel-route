# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
In-memory cache the planner's subscriber fills from inbound notifications and the
SWAP'd controllers read. Replaces Intel's request/poll + CSV reads: the same
`schema.py` models the graph already understands, now sourced from pushed records.

Phase 9: entries carry an insertion timestamp and EXPIRE. Stale data (e.g. a
notification replayed on monitor reconnect, or a feed that has gone quiet) drops
out automatically, so the planner always reasons over "now". Thread-safe.
"""
import threading
import time
from typing import List, Optional

from schema import LiveTrafficData

# How long cached data stays valid (seconds). Live traffic is volatile; conditions
# (weather/trends/events) change slowly. Keep >= the publishers' notification TTL.
LIVE_TRAFFIC_TTL_S = 60
CONDITIONS_TTL_S = 300

_lock = threading.RLock()
# (source_atsign, intersection_name) -> (LiveTrafficData, inserted_at)
_live_traffic: dict = {}
# kind -> { (source_atsign, lat, lon) -> (model, inserted_at) }
_conditions: dict = {"weather": {}, "traffic_trends": {}, "planned_events": {}}


def _purge(store: dict, max_age: float, now: float) -> None:
    for k in [k for k, (_, ts) in store.items() if now - ts > max_age]:
        del store[k]


# ---- live traffic ----------------------------------------------------------
def put_live_traffic(source: str, model: LiveTrafficData) -> None:
    with _lock:
        _live_traffic[(source, model.intersection_name)] = (model, time.time())


def get_live_traffic(max_age_s: float = LIVE_TRAFFIC_TTL_S) -> List[LiveTrafficData]:
    now = time.time()
    with _lock:
        _purge(_live_traffic, max_age_s, now)
        return [m for (m, _) in _live_traffic.values()]


# ---- conditions ------------------------------------------------------------
def put_condition(kind: str, source: str, model) -> None:
    loc = model.location_coordinates
    with _lock:
        _conditions[kind][(source, loc.latitude, loc.longitude)] = (model, time.time())


def find_condition(kind: str, latitude: float, longitude: float, proximity: float,
                   max_age_s: float = CONDITIONS_TTL_S) -> Optional[object]:
    now = time.time()
    with _lock:
        _purge(_conditions[kind], max_age_s, now)
        for (m, _) in _conditions[kind].values():
            loc = m.location_coordinates
            if abs(loc.latitude - latitude) <= proximity and abs(loc.longitude - longitude) <= proximity:
                return m
    return None


# ---- introspection ---------------------------------------------------------
def size() -> int:
    return len(get_live_traffic())


def conditions_size(kind: str) -> int:
    now = time.time()
    with _lock:
        _purge(_conditions[kind], CONDITIONS_TTL_S, now)
        return len(_conditions[kind])


def clear() -> None:
    with _lock:
        _live_traffic.clear()
        for k in _conditions:
            _conditions[k].clear()
