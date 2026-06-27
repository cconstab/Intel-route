# Copyright (C) 2026 Intel Corporation / Atsign migration
# SPDX-License-Identifier: Apache-2.0
#
# SWAP (Atsign migration): reads the subscription-fed conditions cache instead of
# data/csv/weather_report.csv. The @weather_feed atSign now publishes WeatherData;
# this controller looks it up by coordinate. Class + RouteStatusInterface unchanged.
# Original preserved as weather_report.py.intel-orig.
from typing import Optional

from controllers.route_interface import RouteStatusInterface
from schema import WeatherData
from atsign import cache
from utils.logging_config import get_logger

logger = get_logger(__name__)


class WeatherReportController(RouteStatusInterface):
    """Weather, sourced from the @weather_feed subscription cache."""

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
        # Match for large areas around ~500x500 Sq.Mtr.
        return 0.005

    def fetch_route_status(self) -> Optional[WeatherData]:
        return cache.find_condition("weather", self.latitude, self.longitude, self.proximity_factor)
