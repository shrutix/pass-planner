"""Pass assembly, contact windows, and coverage statistics.
 
Plain Python with no Skyfield dependency, so all of the scheduling logic can
be tested without orbit propagation.
"""
 
from dataclasses import dataclass
from datetime import datetime
 
# Event codes as returned by Skyfield's find_events.
RISE, CULMINATE, SET = 0, 1, 2
 
 
@dataclass(frozen=True)
class Event:
    time: datetime
    code: int  # RISE, CULMINATE, or SET
    elevation_deg: float
    azimuth_deg: float
 
 
@dataclass(frozen=True)
class Pass:
    satellite: str
    norad_id: str
    start: datetime  # rises above the elevation mask
    peak: datetime  # highest point
    end: datetime  # sets below the elevation mask
    max_elevation_deg: float
    start_azimuth_deg: float
    end_azimuth_deg: float
 
    @property
    def duration_s(self):
        return (self.end - self.start).total_seconds()
 
 
@dataclass(frozen=True)
class Coverage:
    contact_count: int  # distinct contact windows after merging overlaps
    contact_seconds: float
    coverage_fraction: float  # share of the analysis window with a satellite in view
    longest_gap_seconds: float
    gaps: tuple  # ((gap_start, gap_end), ...)
 
 
def assemble_passes(events, satellite, norad_id):
    """Turn rise / culminate / set events into complete passes.
 
    Only a full rise -> culminate -> set sequence becomes a pass. Anything
    else is dropped: a pass already in progress at the start of the search
    window (no rise), one still in progress at the end (no set), and stray
    culminations.
    """
    passes = []
    rise = peak = None
    for event in sorted(events, key=lambda e: e.time):
        if event.code == RISE:
            rise, peak = event, None
        elif event.code == CULMINATE:
            peak = event if rise is not None else None
        elif event.code == SET:
            if rise is not None and peak is not None:
                passes.append(
                    Pass(
                        satellite=satellite,
                        norad_id=norad_id,
                        start=rise.time,
                        peak=peak.time,
                        end=event.time,
                        max_elevation_deg=peak.elevation_deg,
                        start_azimuth_deg=rise.azimuth_deg,
                        end_azimuth_deg=event.azimuth_deg,
                    )
                )
            rise = peak = None
        else:
            raise ValueError(f"Unknown event code: {event.code}")
    return passes
 
 
def filter_passes(passes, min_elevation_deg=0.0, min_duration_s=0.0):
    """Keep passes that are high enough and long enough to be usable contacts."""
    return [
        p
        for p in passes
        if p.max_elevation_deg >= min_elevation_deg and p.duration_s >= min_duration_s
    ]
 
 
def merge_windows(intervals):
    """Combine overlapping or touching (start, end) intervals into a sorted union."""
    merged = []
    for start, end in sorted(intervals):
        if end < start:
            raise ValueError(f"Interval ends before it starts: {start} to {end}")
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
 
 
def contact_windows(passes):
    """Merged windows during which at least one satellite is in view."""
    return merge_windows([(p.start, p.end) for p in passes])
 
 
def coverage_summary(windows, start, end):
    """Summarize how much of [start, end] is covered by the given windows.
 
    Windows are merged and clipped to the analysis window first. A window with
    no contact at all has a single gap equal to the whole window.
    """
    if end <= start:
        raise ValueError("The analysis window must end after it starts.")
 
    clipped = []
    for window_start, window_end in merge_windows(windows):
        s, e = max(window_start, start), min(window_end, end)
        if e > s:
            clipped.append((s, e))
 
    gaps, cursor = [], start
    for s, e in clipped:
        if s > cursor:
            gaps.append((cursor, s))
        cursor = e
    if cursor < end:
        gaps.append((cursor, end))
 
    total = (end - start).total_seconds()
    contact = sum((e - s).total_seconds() for s, e in clipped)
    longest = max(((b - a).total_seconds() for a, b in gaps), default=0.0)
    return Coverage(
        contact_count=len(clipped),
        contact_seconds=contact,
        coverage_fraction=contact / total,
        longest_gap_seconds=longest,
        gaps=tuple(gaps),
    )