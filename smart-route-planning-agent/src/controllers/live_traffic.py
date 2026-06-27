# Copyright (C) 2026 Intel Corporation / Atsign migration
# SPDX-License-Identifier: Apache-2.0
#
# SWAP (Atsign migration): the ONLY changed controller. The original polled each
# intersection's REST API (`requests.get(host + endpoint)`) from a static host
# list in config.json. It now reads the in-memory cache that the planner's atSign
# subscriber fills from encrypted, pushed `live_traffic.smartroute` notifications.
#
# The class name, the `RouteStatusInterface` contract, and `fetch_route_status()`'s
# return type are unchanged, so the LangGraph graph and route_service are untouched.
# Original preserved as live_traffic.py.intel-orig for diffing.
from typing import List, Optional

from controllers.route_interface import RouteStatusInterface
from schema import LiveTrafficData
from atsign import cache
from utils.logging_config import get_logger

logger = get_logger(__name__)


class LiveTrafficController(RouteStatusInterface):
    """Live traffic, sourced from the subscription-fed cache (no polling, no host list)."""

    def __init__(
        self, latitude: Optional[float] = None, longitude: Optional[float] = None
    ):
        self._latitude = latitude
        self._longitude = longitude

    @property
    def latitude(self) -> Optional[float]:
        return self._latitude

    @property
    def longitude(self) -> Optional[float]:
        return self._longitude

    @property
    def proximity_factor(self) -> float:
        """Exact coordinate match, as in the original."""
        return 0.0

    def fetch_route_status(self) -> List[LiveTrafficData]:
        """
        Return live traffic for all intersections from the subscription cache.

        Same shape the realtime LangGraph node already consumes; the records arrived
        as encrypted notifications from intersection atSigns instead of REST polls.
        """
        records = cache.get_live_traffic()
        logger.info(
            f"Live traffic from subscription cache: {len(records)} intersection(s)"
        )
        return records
