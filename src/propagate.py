"""Orbit propagation with Skyfield: passes, ground tracks, and element age.
 
This is the only module that imports Skyfield. It is a thin layer: all
scheduling logic lives in windows.py and groundtrack.py.
"""
 
from dataclasses import dataclass
from datetime import timezone
 
import numpy as np
from skyfield.api import EarthSatellite, load, wgs84
 
from windows import Event, assemble_passes
 
_TIMESCALE = load.timescale()
 
 
@dataclass(frozen=True)
class Tracked:
    name: str
    norad_id: str  # kept as text so six-digit catalog numbers need no special case
    satellite: EarthSatellite
 
 
def _require_aware(moment, label):
    if moment.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware (use UTC).")
    return moment.astimezone(timezone.utc)
 
 
def satellites_from_rows(rows):
    """Build satellites from OMM CSV rows.
 
    Returns (tracked, skipped). A row that cannot be turned into a satellite
    goes into ``skipped`` as (name, reason) instead of stopping the load.
    """
    tracked, skipped = [], []
    for row in rows:
        name = (row.get("OBJECT_NAME") or "?").strip()
        try:
            satellite = EarthSatellite.from_omm(_TIMESCALE, row)
        except (KeyError, ValueError, TypeError) as exc:
            skipped.append((name, f"{type(exc).__name__}: {exc}"))
            continue
        tracked.append(Tracked(name, str(row["NORAD_CAT_ID"]).strip(), satellite))
    return tracked, skipped
 
 
def epoch_age_days(tracked, when):
    """Days between the element set's epoch and ``when`` (always positive).
 
    Accuracy degrades the further you are from the epoch, typically over a
    couple of weeks.
    """
    when = _require_aware(when, "when")
    return abs(_TIMESCALE.from_datetime(when) - tracked.satellite.epoch)
 
 
def find_passes(tracked, station, start, end, min_elevation_deg=10.0):
    """Predict passes of one satellite over a station between start and end.
 
    Passes already in progress at ``start`` or still in progress at ``end``
    are omitted (see windows.assemble_passes).
    """
    start = _require_aware(start, "start")
    end = _require_aware(end, "end")
    if end <= start:
        raise ValueError("end must be after start.")
 
    site = wgs84.latlon(station.latitude_deg, station.longitude_deg, station.elevation_m)
    satellite = tracked.satellite
    times, codes = satellite.find_events(
        site,
        _TIMESCALE.from_datetime(start),
        _TIMESCALE.from_datetime(end),
        altitude_degrees=min_elevation_deg,
    )
    if len(codes) == 0:
        return []
 
    altitude, azimuth, _distance = (satellite - site).at(times).altaz()
    events = [
        Event(moment, int(code), float(alt), float(az))
        for moment, code, alt, az in zip(
            times.utc_datetime(), codes, altitude.degrees, azimuth.degrees
        )
    ]
    return assemble_passes(events, tracked.name, tracked.norad_id)
 
 
def ground_track(tracked, start, end, step_s=30):
    """Sample the sub-satellite point. Returns (times, latitudes, longitudes)."""
    start = _require_aware(start, "start")
    end = _require_aware(end, "end")
    if end <= start or step_s <= 0:
        raise ValueError("end must be after start, and step_s must be positive.")
 
    count = int((end - start).total_seconds() // step_s) + 1
    seconds = (
        start.second + start.microsecond / 1e6 + np.arange(count) * float(step_s)
    )
    t = _TIMESCALE.utc(start.year, start.month, start.day, start.hour, start.minute, seconds)
    subpoint = wgs84.subpoint_of(tracked.satellite.at(t))
    return (
        list(t.utc_datetime()),
        subpoint.latitude.degrees.tolist(),
        subpoint.longitude.degrees.tolist(),
    )