# Copyright (C) 2026 Intel Corporation / Atsign migration
# SPDX-License-Identifier: Apache-2.0
#
# SWAP (Atsign migration): reads the subscription-fed conditions cache instead of
# data/csv/traffic_trends.csv. The @traffic_trends_feed atSign now publishes
# TrafficTrendsData; this controller looks it up by coordinate. Class +
# RouteStatusInterface unchanged. Original preserved as traffic_trends.py.intel-orig.
from typing import Optional

from controllers.route_interface import RouteStatusInterface
from schema import TrafficTrendsData
from atsign import cache
from utils.logging_config import get_logger

logger = get_logger(__name__)


class TrafficTrendsController(RouteStatusInterface):
    """Historical traffic trends, sourced from the @traffic_trends_feed cache."""

    def __init__(self, latitude: float, longitude: float):
        self._latitude = latitude
        self._longitude = longitude

    @property
    def latitude(self) -> float:
        return self._latitude

    @property
    def longitude(self) -> float:
        return self._longitude

    @property
    def proximity_factor(self) -> float:
        # Match for smaller areas around ~55x55 Sq.Mtr.
        return 0.0005

    def fetch_route_status(self) -> Optional[TrafficTrendsData]:
        return cache.find_condition("traffic_trends", self.latitude, self.longitude, self.proximity_factor)
