"""Helpers for drawing ground tracks on a flat map (plain Python)."""
 
 
def normalize_longitude(lon):
    """Wrap a longitude into [-180, 180)."""
    return ((lon + 180.0) % 360.0) - 180.0
 
 
def normalize_longitudes(lons):
    return [normalize_longitude(lon) for lon in lons]
 
 
def split_at_antimeridian(lats, lons, jump_deg=180.0):
    """Split a track into segments wherever it crosses the +/-180 line.
 
    A flat map would otherwise draw a line straight across the whole map
    between the last point before the crossing and the first point after it.
    Returns a list of (lats, lons) tuples.
    """
    if len(lats) != len(lons):
        raise ValueError("lats and lons must be the same length.")
 
    segments, seg_lats, seg_lons = [], [], []
    for lat, lon in zip(lats, normalize_longitudes(lons)):
        if seg_lons and abs(lon - seg_lons[-1]) > jump_deg:
            segments.append((seg_lats, seg_lons))
            seg_lats, seg_lons = [], []
        seg_lats.append(lat)
        seg_lons.append(lon)
    if seg_lons:
        segments.append((seg_lats, seg_lons))
    return segments
 
 
def with_gaps(lats, lons):
    """Flatten segments into single lists with None between them.
 
    Plotly treats None as a break in a line, so the result draws as separate
    pieces without wrap-around lines.
    """
    out_lats, out_lons = [], []
    for index, (seg_lats, seg_lons) in enumerate(split_at_antimeridian(lats, lons)):
        if index:
            out_lats.append(None)
            out_lons.append(None)
        out_lats.extend(seg_lats)
        out_lons.extend(seg_lons)
    return out_lats, out_lons