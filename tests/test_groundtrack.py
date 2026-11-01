import dataclasses
import math
 
import pytest
 
from groundtrack import (
    normalize_longitude,
    normalize_longitudes,
    split_at_antimeridian,
    with_gaps,
)
from stations import PRESETS, Station
 
 
# --- longitude wrapping ---
 
@pytest.mark.parametrize(
    "lon, expected",
    [(0, 0), (179, 179), (-179, -179), (190, -170), (-190, 170), (360, 0), (540, -180)],
)
def test_normalize_longitude(lon, expected):
    assert normalize_longitude(lon) == pytest.approx(expected)
 
 
def test_normalize_longitudes_maps_a_list():
    assert normalize_longitudes([190, -190]) == pytest.approx([-170, 170])
 
 
# --- antimeridian splitting ---
 
def test_track_that_never_crosses_stays_in_one_segment():
    lats, lons = [0, 1, 2], [10, 20, 30]
    assert split_at_antimeridian(lats, lons) == [([0, 1, 2], [10, 20, 30])]
 
 
def test_eastbound_crossing_splits_into_two_segments():
    segments = split_at_antimeridian([0, 1, 2, 3], [170, 178, -178, -170])
    assert segments == [([0, 1], [170, 178]), ([2, 3], [-178, -170])]
 
 
def test_westbound_crossing_splits_too():
    segments = split_at_antimeridian([0, 1, 2], [-175, -179, 179])
    assert len(segments) == 2
 
 
def test_two_crossings_make_three_segments():
    lons = [170, -170, -10, 170, -170]
    assert len(split_at_antimeridian([0] * 5, lons)) == 3
 
 
def test_a_big_jump_that_is_not_the_antimeridian_is_still_split():
    # The rule is purely "more than 180 degrees between consecutive points".
    assert len(split_at_antimeridian([0, 0], [-100, 100.5])) == 2
 
 
def test_empty_track_gives_no_segments():
    assert split_at_antimeridian([], []) == []
 
 
def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        split_at_antimeridian([0, 1], [0])
 
 
def test_unwrapped_longitudes_are_normalized_before_splitting():
    # 179 -> 181 is really 179 -> -179: a 2 degree move that crosses the line
    segments = split_at_antimeridian([5, 6], [179, 181])
    assert len(segments) == 2
    assert segments[0] == ([5], [179])
    assert segments[1][0] == [6] and segments[1][1] == pytest.approx([-179])
 
 
def test_with_gaps_inserts_none_between_segments():
    lats, lons = with_gaps([0, 1, 2, 3], [170, 178, -178, -170])
    assert lats == [0, 1, None, 2, 3]
    assert lons == [170, 178, None, -178, -170]
 
 
def test_with_gaps_leaves_a_single_segment_alone():
    assert with_gaps([0, 1], [10, 20]) == ([0, 1], [10, 20])
 
 
# --- stations --- 
 
def test_station_defaults_to_sea_level():
    assert Station("X", 10.0, 20.0).elevation_m == 0.0
 
 
@pytest.mark.parametrize("lat", [-90.1, 90.1, float("nan")])
def test_bad_latitude_is_rejected(lat):
    with pytest.raises(ValueError, match="Latitude"):
        Station("X", lat, 0.0)
 
 
@pytest.mark.parametrize("lon", [-180.1, 180.1, float("nan")])
def test_bad_longitude_is_rejected(lon):
    with pytest.raises(ValueError, match="Longitude"):
        Station("X", 0.0, lon)
 
 
@pytest.mark.parametrize("lat, lon", [(90, 180), (-90, -180), (0, 0)])
def test_edge_coordinates_are_accepted(lat, lon):
    assert Station("X", lat, lon).latitude_deg == lat
 
 
def test_stations_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Station("X", 0, 0).latitude_deg = 5
 
 
def test_presets_are_valid_and_labelled_as_examples():
    assert PRESETS
    for label, station in PRESETS.items():
        assert "example" in label.lower()
        assert math.isfinite(station.latitude_deg) and math.isfinite(station.longitude_deg)