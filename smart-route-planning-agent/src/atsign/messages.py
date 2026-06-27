# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Outbound message models the planner PUSHES to its front-ends:
  - RoutePush  -> commuter app  (key `route.smartroute`)
  - StatusPush -> operator console (key `status.smartroute`)

Kept as small Pydantic models so both the Python operator console and the Dart
commuter app parse the same JSON (cross-language interop already proven).
"""
from typing import List

from pydantic import BaseModel

from config import GPX_DIR
from utils.gpx_parser import MapDataParser


class RoutePush(BaseModel):
    route_name: str
    distance_km: float
    reason: str
    rerouted: bool
    points: List[List[float]]  # [[lat, lon], ...] (downsampled for transport)


class StatusPush(BaseModel):
    optimal_route: str
    distance_km: float
    reason: str
    rerouted: bool
    agent_status: str
    intersections: List[dict] = []  # [{name, lat, lon, density}, ...]
    points: List[List[float]] = []  # optimal-route geometry for the console map


def route_points(route_name: str, max_points: int = 120) -> List[List[float]]:
    """Downsampled [lat, lon] geometry for a route, for the map widget / console."""
    data = MapDataParser(GPX_DIR / route_name).get_route_data()
    tps = data["tracks"][0]["track_points"]
    step = max(1, len(tps) // max_points)
    return [[tp["lat"], tp["lon"]] for tp in tps[::step]]
