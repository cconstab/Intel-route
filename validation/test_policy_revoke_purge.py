#!/usr/bin/env python3
"""
Deterministic test: revoking a publisher immediately purges its cached data, so the
planner stops rerouting on a now-denied source this cycle (not after the 60s TTL).

Covers cache.drop_source() and the planner's on_record policy handler.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smart-route-planning-agent", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from atsign import cache, roles
from schema import GeoCoordinates, LiveTrafficData, WeatherData, WeatherStatus, IncidentStatus  # noqa: F401

BRAVO = roles.atsign_for("intxn_market_st")
CHARLIE = roles.atsign_for("intxn_5th_ave")
POLICY = roles.atsign_for("policy")
NS = roles.namespace()


def lt(name):
    return LiveTrafficData(
        location_coordinates=GeoCoordinates(latitude=37.5, longitude=-122.0),
        intersection_name=name, timestamp="2026-01-01T00:00:00",
        traffic_density=30, traffic_description="jam",
        weather_status=WeatherStatus.CLEAR, incident_status=IncidentStatus.CROWDING,
    )


def test_drop_source():
    cache.clear()
    cache.put_live_traffic(BRAVO, lt("Market St"))
    cache.put_live_traffic(CHARLIE, lt("5th Ave"))
    cache.put_condition("weather", BRAVO, WeatherData(
        location_coordinates=GeoCoordinates(latitude=37.5, longitude=-122.0),
        weather_condition=WeatherStatus.CLEAR, temperature=68.0, visibility=10.0))
    assert cache.size() == 2
    dropped = cache.drop_source(BRAVO)
    assert dropped == 2, dropped                       # 1 live_traffic + 1 weather
    names = [m.intersection_name for m in cache.get_live_traffic()]
    assert names == ["5th Ave"], names                 # only charlie remains
    assert cache.conditions_size("weather") == 0
    print(f"drop_source removed {dropped} record(s); charlie untouched")


def test_on_record_revoke_purges():
    import planner_service as ps
    cache.clear()
    ps.ALLOW.clear(); ps.ALLOW.update({BRAVO, CHARLIE})
    cache.put_live_traffic(BRAVO, lt("Market St"))     # bravo has an active incident cached
    cache.put_live_traffic(CHARLIE, lt("5th Ave"))
    assert cache.size() == 2

    # policy update that revokes bravo (grants only charlie)
    key = f"@alpha:policy.{NS}{POLICY}"
    value = '{"grants": ["%s"], "issued_by": "%s"}' % (CHARLIE, POLICY)
    ps.on_record(POLICY, key, value, {})

    assert ps.ALLOW == {CHARLIE}, ps.ALLOW
    names = [m.intersection_name for m in cache.get_live_traffic()]
    assert names == ["5th Ave"], names                 # bravo's incident purged immediately
    print("on_record revoke -> bravo purged same cycle; ALLOW == {charlie}")

    # a later record from revoked bravo is dropped at ingestion (stays out)
    ps.on_record(BRAVO, f"@alpha:live_traffic.{NS}{BRAVO}", "x", {})
    assert [m.intersection_name for m in cache.get_live_traffic()] == ["5th Ave"]
    print("post-revoke bravo record dropped at ingestion (no re-cache)")


if __name__ == "__main__":
    test_drop_source()
    test_on_record_revoke_purges()
    print("\nPASS: revocation purges cached data immediately (no lingering reroute / flicker).")
