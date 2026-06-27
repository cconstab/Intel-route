# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
The wire contract: the encrypted JSON exchanged between atSigns IS the Intel
Pydantic model (`schema.py`) serialized. Publisher and planner share these exact
models; the Dart commuter app reads the same JSON fields (interop verified in the
spike). Record (key) names live in RECORDS; all under the `smartroute` namespace.
"""
from schema import (
    LiveTrafficData,
    WeatherData,
    TrafficTrendsData,
    PlannedEventsData,
)

# key name (without namespace) -> model, per blueprint conventions
RECORDS = {
    "live_traffic": LiveTrafficData,
    "weather": WeatherData,
    "traffic_trends": TrafficTrendsData,
    "planned_events": PlannedEventsData,
}


def encode(model) -> str:
    """Serialize a schema model to the on-wire JSON string."""
    return model.model_dump_json()


def decode(key_name: str, value: str):
    """Parse an on-wire JSON string back into the right schema model."""
    model = RECORDS[key_name]
    return model.model_validate_json(value)


def key_name_from_atkey(at_key: str) -> str:
    """Extract the record name from a full atKey.

    Handles both renderings seen on the wire: Dart's `@to:live_traffic.smartroute@from`
    and atsdk's dot-less `@to:live_trafficsmartroute@from`. Strips the `@to:` prefix,
    the `@from` suffix, and the trailing namespace.
    """
    from atsign import roles

    core = at_key.split(":", 1)[-1]   # live_traffic.smartroute@from  | live_trafficsmartroute@from
    core = core.split("@", 1)[0]      # live_traffic.smartroute       | live_trafficsmartroute
    ns = roles.namespace()
    if core.endswith(ns):
        core = core[: -len(ns)]
    return core.rstrip(".")           # live_traffic
