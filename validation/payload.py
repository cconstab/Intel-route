# Copyright (C) 2026 Intel Corporation / Atsign migration spike
# SPDX-License-Identifier: Apache-2.0
"""
Shared wire contract for the spike.

Mirrors the field shape of Intel's `schema.py::LiveTrafficData` so that the
exact same payload the planner already understands travels over the Atsign
notification channel. Kept dependency-free (plain dict <-> JSON) so the spike
needs nothing beyond `atsdk`; the real build can swap this for the Pydantic
models in `schema.py` unchanged.
"""
import json
from typing import Any


def make_live_traffic(
    intersection_name: str,
    latitude: float,
    longitude: float,
    traffic_density: int,
    timestamp: str,
    weather_status: str = "Clear",
    incident_status: str = "clear",
    traffic_description: str | None = None,
) -> dict[str, Any]:
    """Build a LiveTrafficData-shaped record (matches schema.py field names)."""
    return {
        "location_coordinates": {"latitude": latitude, "longitude": longitude},
        "intersection_name": intersection_name,
        "timestamp": timestamp,
        "traffic_density": traffic_density,
        "traffic_description": traffic_description,
        "weather_status": weather_status,
        "incident_status": incident_status,
    }


# The exact set of fields the planner's LiveTrafficController expects to read.
REQUIRED_FIELDS = {
    "location_coordinates",
    "intersection_name",
    "timestamp",
    "traffic_density",
    "weather_status",
    "incident_status",
}


def encode(record: dict[str, Any]) -> str:
    return json.dumps(record, separators=(",", ":"))


def decode(value: str) -> dict[str, Any]:
    return json.loads(value)


def validate(record: dict[str, Any]) -> list[str]:
    """Return a list of problems; empty list means the record is well-formed."""
    problems = []
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        problems.append(f"missing fields: {sorted(missing)}")
    coords = record.get("location_coordinates", {})
    if not isinstance(coords, dict) or "latitude" not in coords or "longitude" not in coords:
        problems.append("location_coordinates must have latitude+longitude")
    if not isinstance(record.get("traffic_density"), int):
        problems.append("traffic_density must be an int")
    return problems
