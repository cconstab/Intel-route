# Copyright (C) 2026 Intel Corporation / Atsign migration
# SPDX-License-Identifier: Apache-2.0
#
# SWAP (Atsign migration): reads the subscription-fed conditions cache instead of
# data/csv/planned_events.csv. The @events_feed atSign now publishes
# PlannedEventsData; this controller looks it up by coordinate. Class +
# RouteStatusInterface unchanged. Original preserved as planned_events.py.intel-orig.
from typing import Optional

from controllers.route_interface import RouteStatusInterface
from schema import PlannedEventsData
from atsign import cache
from utils.logging_config import get_logger

logger = get_logger(__name__)


class PlannedEventsController(RouteStatusInterface):
    """Planned events, sourced from the @events_feed subscription cache."""

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
        # Match for very large areas around ~1x1 Sq.Kms.
        return 0.01

    def fetch_route_status(self) -> Optional[PlannedEventsData]:
        return cache.find_condition("planned_events", self.latitude, self.longitude, self.proximity_factor)
