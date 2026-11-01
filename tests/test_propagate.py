"""Tests for the Skyfield layer.
 
These check physical invariants (ordering, bounds, geometry) rather than exact
predicted times, so they hold for any valid orbit and need no network access.
Skipped automatically when Skyfield is not installed.
"""
 
import math
from datetime import datetime, timedelta, timezone
 
import pytest
 
pytest.importorskip("skyfield")
 
from propagate import (  # noqa: E402
    epoch_age_days,
    find_passes,
    ground_track,
    satellites_from_rows,
)
from sample_data import ISS_LIKE, POLAR  # noqa: E402
from stations import Station  # noqa: E402
 
START = datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)  # the sample epoch
END = START + timedelta(hours=24)
 
SAN_FRANCISCO = Station("San Francisco", 37.7749, -122.4194, 16.0)
SVALBARD = Station("Svalbard", 78.2298, 15.39)
EQUATOR = Station("Equator", 0.0, 0.0)
 
 
@pytest.fixture(scope="module")
def tracked():
    sats, skipped = satellites_from_rows([ISS_LIKE, POLAR])
    assert not skipped
    return {t.name: t for t in sats}
 
 
def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance on a spherical Earth."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(a))
 
 
# --- loading ---
 
def test_rows_become_tracked_satellites(tracked):
    assert set(tracked) == {"SAMPLE ISS-LIKE", "SAMPLE POLAR"}
    assert tracked["SAMPLE POLAR"].norad_id == "123456"
 
 
def test_a_bad_row_is_skipped_not_fatal():
    broken = {k: v for k, v in ISS_LIKE.items() if k != "BSTAR"}
    sats, skipped = satellites_from_rows([broken, POLAR])
    assert [t.name for t in sats] == ["SAMPLE POLAR"]
    assert len(skipped) == 1 and skipped[0][0] == "SAMPLE ISS-LIKE"
 
 
# --- epoch age ---
 
def test_epoch_age_is_zero_at_the_epoch(tracked):
    assert epoch_age_days(tracked["SAMPLE POLAR"], START) < 1e-3
 
 
def test_epoch_age_counts_days_in_either_direction(tracked):
    sat = tracked["SAMPLE POLAR"]
    assert epoch_age_days(sat, START + timedelta(days=3)) == pytest.approx(3, abs=1e-3)
    assert epoch_age_days(sat, START - timedelta(days=2)) == pytest.approx(2, abs=1e-3)
 
 
def test_naive_datetimes_are_rejected(tracked):
    with pytest.raises(ValueError, match="timezone"):
        epoch_age_days(tracked["SAMPLE POLAR"], datetime(2026, 10, 30))
 
 
# --- passes ---
 
def test_passes_are_well_formed(tracked):
    passes = find_passes(tracked["SAMPLE POLAR"], SAN_FRANCISCO, START, END, min_elevation_deg=10)
    assert passes, "a polar LEO satellite should pass a mid-latitude site within 24 hours"
    for p in passes:
        assert p.start < p.peak < p.end
        assert START <= p.start and p.end <= END
        assert p.max_elevation_deg >= 10 - 0.5
        assert p.max_elevation_deg <= 90
        assert 30 <= p.duration_s <= 20 * 60  # a LEO pass lasts minutes
        assert 0 <= p.start_azimuth_deg <= 360 and 0 <= p.end_azimuth_deg <= 360
        assert (p.satellite, p.norad_id) == ("SAMPLE POLAR", "123456")
 
 
def test_passes_do_not_overlap_for_one_satellite(tracked):
    passes = find_passes(tracked["SAMPLE POLAR"], SAN_FRANCISCO, START, END)
    for earlier, later in zip(passes, passes[1:]):
        assert earlier.end <= later.start
 
 
def test_a_higher_elevation_mask_gives_fewer_or_equal_passes(tracked):
    sat = tracked["SAMPLE POLAR"]
    low = find_passes(sat, SAN_FRANCISCO, START, END, min_elevation_deg=5)
    high = find_passes(sat, SAN_FRANCISCO, START, END, min_elevation_deg=40)
    assert len(high) <= len(low)
 
 
def test_a_polar_orbit_sees_a_polar_station_more_often_than_an_equatorial_one(tracked):
    sat = tracked["SAMPLE POLAR"]
    polar_site = find_passes(sat, SVALBARD, START, END, min_elevation_deg=5)
    equatorial_site = find_passes(sat, EQUATOR, START, END, min_elevation_deg=5)
    assert len(polar_site) > len(equatorial_site)
 
 
def test_an_orbit_never_visits_stations_far_beyond_its_inclination(tracked):
    # A 51.6 degree orbit stays well below Svalbard's 78 degrees north, so
    # nothing should ever rise above a 30 degree mask there.
    assert find_passes(tracked["SAMPLE ISS-LIKE"], SVALBARD, START, END, min_elevation_deg=30) == []
 
 
def test_naive_search_window_is_rejected(tracked):
    with pytest.raises(ValueError, match="timezone"):
        find_passes(tracked["SAMPLE POLAR"], SAN_FRANCISCO, datetime(2026, 10, 30), END)
 
 
def test_reversed_search_window_is_rejected(tracked):
    with pytest.raises(ValueError):
        find_passes(tracked["SAMPLE POLAR"], SAN_FRANCISCO, END, START)
 
 
# --- ground track ---
 
def test_ground_track_shape(tracked):
    times, lats, lons = ground_track(tracked["SAMPLE POLAR"], START, START + timedelta(hours=2), step_s=30)
    assert len(times) == len(lats) == len(lons) == 2 * 3600 // 30 + 1
    assert times[0] == START
    assert (times[1] - times[0]).total_seconds() == pytest.approx(30)
 
 
@pytest.mark.parametrize("name, inclination", [("SAMPLE ISS-LIKE", 51.64), ("SAMPLE POLAR", 97.5)])
def test_latitude_never_exceeds_the_orbit_inclination(tracked, name, inclination):
    _t, lats, lons = ground_track(tracked[name], START, START + timedelta(hours=6), step_s=60)
    limit = min(inclination, 180 - inclination) + 1.0
    assert max(abs(lat) for lat in lats) <= limit
    assert all(-180 <= lon <= 180 for lon in lons)
 
 
def test_ground_track_moves_smoothly(tracked):
    # Ground speed is about 7 km/s, so 30 s steps should move roughly 200 km.
    _t, lats, lons = ground_track(tracked["SAMPLE POLAR"], START, START + timedelta(hours=3), step_s=30)
    steps = [distance_km(a, b, c, d) for a, b, c, d in zip(lats, lons, lats[1:], lons[1:])]
    assert 100 < min(steps) and max(steps) < 400
 
 
def test_ground_track_rejects_bad_arguments(tracked):
    sat = tracked["SAMPLE POLAR"]
    with pytest.raises(ValueError):
        ground_track(sat, START, START + timedelta(hours=1), step_s=0)
    with pytest.raises(ValueError):
        ground_track(sat, START, START)
    with pytest.raises(ValueError, match="timezone"):
        ground_track(sat, datetime(2026, 10, 30), END)