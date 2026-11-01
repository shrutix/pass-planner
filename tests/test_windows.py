from datetime import datetime, timedelta, timezone
 
import pytest
 
from windows import (
    CULMINATE,
    RISE,
    SET,
    Coverage,
    Event,
    Pass,
    assemble_passes,
    contact_windows,
    coverage_summary,
    filter_passes,
    merge_windows,
)
 
T0 = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
 
 
def at(minutes):
    return T0 + timedelta(minutes=minutes)
 
 
def ev(minutes, code, elevation=0.0, azimuth=0.0):
    return Event(at(minutes), code, elevation, azimuth)
 
 
def make_pass(start, end, elevation=30.0, name="SAT", norad="1"):
    mid = start + (end - start) / 2
    return Pass(name, norad, at(start), at(mid), at(end), elevation, 10.0, 200.0)
 
 
# --- assemble_passes ---
 
def test_a_complete_sequence_becomes_a_pass():
    events = [ev(0, RISE, 10, 30), ev(4, CULMINATE, 62.5, 90), ev(8, SET, 10, 160)]
    (p,) = assemble_passes(events, "FLOCK 1", "4242")
    assert (p.satellite, p.norad_id) == ("FLOCK 1", "4242")
    assert (p.start, p.peak, p.end) == (at(0), at(4), at(8))
    assert p.max_elevation_deg == 62.5
    assert (p.start_azimuth_deg, p.end_azimuth_deg) == (30, 160)
    assert p.duration_s == 480
 
 
def test_several_passes_are_returned_in_order():
    events = [
        ev(0, RISE), ev(4, CULMINATE, 40), ev(8, SET),
        ev(100, RISE), ev(104, CULMINATE, 70), ev(108, SET),
    ]
    passes = assemble_passes(events, "S", "1")
    assert [p.max_elevation_deg for p in passes] == [40, 70]
 
 
def test_unsorted_events_are_sorted_first():
    events = [ev(8, SET), ev(0, RISE), ev(4, CULMINATE, 40)]
    assert len(assemble_passes(events, "S", "1")) == 1
 
 
def test_pass_already_in_progress_at_the_start_is_dropped():
    events = [ev(1, CULMINATE, 50), ev(4, SET), ev(100, RISE), ev(104, CULMINATE, 60), ev(108, SET)]
    passes = assemble_passes(events, "S", "1")
    assert [p.start for p in passes] == [at(100)]
 
 
def test_pass_still_in_progress_at_the_end_is_dropped():
    events = [ev(0, RISE), ev(4, CULMINATE, 40), ev(8, SET), ev(100, RISE), ev(104, CULMINATE, 60)]
    assert len(assemble_passes(events, "S", "1")) == 1
 
 
def test_rise_and_set_without_a_culmination_is_dropped():
    assert assemble_passes([ev(0, RISE), ev(8, SET)], "S", "1") == []
 
 
def test_a_second_rise_discards_the_unfinished_first_one():
    events = [ev(0, RISE), ev(4, CULMINATE, 40), ev(10, RISE), ev(14, CULMINATE, 55), ev(18, SET)]
    (p,) = assemble_passes(events, "S", "1")
    assert (p.start, p.max_elevation_deg) == (at(10), 55)
 
 
def test_no_events_gives_no_passes():
    assert assemble_passes([], "S", "1") == []
 
 
def test_unknown_event_code_raises():
    with pytest.raises(ValueError, match="Unknown event code"):
        assemble_passes([ev(0, 7)], "S", "1")
 
 
# --- filter_passes ---

def test_filter_by_elevation_and_duration():
    short_low = make_pass(0, 2, elevation=12)
    long_low = make_pass(10, 20, elevation=12)
    short_high = make_pass(30, 32, elevation=70)
    long_high = make_pass(40, 50, elevation=70)
    passes = [short_low, long_low, short_high, long_high]
 
    assert filter_passes(passes) == passes
    assert filter_passes(passes, min_elevation_deg=45) == [short_high, long_high]
    assert filter_passes(passes, min_duration_s=300) == [long_low, long_high]
    assert filter_passes(passes, 45, 300) == [long_high]
 
 
def test_filter_bounds_are_inclusive():
    p = make_pass(0, 5, elevation=30)
    assert filter_passes([p], min_elevation_deg=30, min_duration_s=300) == [p]
 
 
# --- merge_windows ---

def test_overlapping_windows_merge():
    assert merge_windows([(at(0), at(10)), (at(5), at(15))]) == [(at(0), at(15))]
 
 
def test_touching_windows_merge():
    assert merge_windows([(at(0), at(10)), (at(10), at(20))]) == [(at(0), at(20))]
 
 
def test_separate_windows_stay_separate_and_sorted():
    assert merge_windows([(at(30), at(40)), (at(0), at(10))]) == [(at(0), at(10)), (at(30), at(40))]
 
 
def test_a_window_inside_another_is_absorbed():
    assert merge_windows([(at(0), at(60)), (at(10), at(20))]) == [(at(0), at(60))]
 
 
def test_merge_of_nothing_is_empty():
    assert merge_windows([]) == []
 
 
def test_backwards_interval_raises():
    with pytest.raises(ValueError):
        merge_windows([(at(10), at(0))])
 
 
def test_contact_windows_combine_passes_from_different_satellites():
    passes = [make_pass(0, 10, name="A"), make_pass(8, 18, name="B"), make_pass(60, 70, name="A")]
    assert contact_windows(passes) == [(at(0), at(18)), (at(60), at(70))]
 
 
# --- coverage_summary ---
 
def test_coverage_of_two_windows_with_gaps_on_every_side():
    windows = [(at(10), at(20)), (at(50), at(60))]
    cov = coverage_summary(windows, at(0), at(100))
    assert isinstance(cov, Coverage)
    assert cov.contact_count == 2
    assert cov.contact_seconds == 20 * 60
    assert cov.coverage_fraction == pytest.approx(0.2)
    assert cov.gaps == ((at(0), at(10)), (at(20), at(50)), (at(60), at(100)))
    assert cov.longest_gap_seconds == 40 * 60
 
 
def test_no_windows_means_one_gap_covering_everything():
    cov = coverage_summary([], at(0), at(100))
    assert cov.contact_count == 0 and cov.coverage_fraction == 0
    assert cov.gaps == ((at(0), at(100)),)
    assert cov.longest_gap_seconds == 100 * 60
 
 
def test_full_coverage_has_no_gaps():
    cov = coverage_summary([(at(-5), at(105))], at(0), at(100))
    assert cov.coverage_fraction == 1
    assert cov.gaps == () and cov.longest_gap_seconds == 0
 
 
def test_windows_are_clipped_to_the_analysis_window():
    cov = coverage_summary([(at(-10), at(10)), (at(90), at(120))], at(0), at(100))
    assert cov.contact_seconds == 20 * 60
    assert cov.contact_count == 2
 
 
def test_windows_entirely_outside_the_window_are_ignored():
    cov = coverage_summary([(at(200), at(210)), (at(-50), at(-40))], at(0), at(100))
    assert cov.contact_count == 0 and cov.coverage_fraction == 0
 
 
def test_overlaps_are_not_double_counted():
    cov = coverage_summary([(at(0), at(10)), (at(5), at(15))], at(0), at(100))
    assert cov.contact_seconds == 15 * 60 and cov.contact_count == 1
 
 
def test_empty_analysis_window_raises():
    with pytest.raises(ValueError):
        coverage_summary([], at(10), at(10))
    with pytest.raises(ValueError):
        coverage_summary([], at(10), at(0))