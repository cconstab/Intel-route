# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
In-memory cache the planner's subscriber fills from inbound notifications and the
SWAP'd controllers read. Replaces Intel's request/poll: the same `LiveTrafficData`
the graph already understands, now sourced from pushed records. Thread-safe.
"""
import threading
from typing import List

from schema import LiveTrafficData

_lock = threading.RLock()
# (source_atsign, intersection_name) -> latest LiveTrafficData
_live_traffic: dict = {}


def put_live_traffic(source: str, model: LiveTrafficData) -> None:
    with _lock:
        _live_traffic[(source, model.intersection_name)] = model


def get_live_traffic() -> List[LiveTrafficData]:
    with _lock:
        return list(_live_traffic.values())


def size() -> int:
    with _lock:
        return len(_live_traffic)


def clear() -> None:
    with _lock:
        _live_traffic.clear()
