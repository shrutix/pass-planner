from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
 
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
 
from gpdata import OrbitDataError, build_query_url, fetch_gp_csv, parse_omm_csv
from groundtrack import with_gaps
from propagate import epoch_age_days, find_passes, ground_track, satellites_from_rows
from stations import PRESETS, Station
from windows import contact_windows, coverage_summary, filter_passes
 
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
STALE_EPOCH_DAYS = 14.0
CUSTOM_STATION = "Custom location"
QUERY_KINDS = {"Group": "group", "Name contains": "name", "Catalog number": "catnr"}
 
st.set_page_config(page_title="Pass & Contact Planner", page_icon="🛰️", layout="wide")
 
 
@dataclass(frozen=True)
class Analysis:
    passes: tuple
    epoch_ages: dict  # NORAD id -> days between the element epoch and the start time
    satellites_used: int
 
 
@st.cache_resource(ttl=1800, show_spinner="Loading orbit data...")
def load_orbit_data(query_kind, query_value):
    url = build_query_url(**{query_kind: query_value})
    result = fetch_gp_csv(url, CACHE_DIR)
    tracked, skipped = satellites_from_rows(parse_omm_csv(result.text))
    return tracked, skipped, result
 
 
@st.cache_data(ttl=3600, show_spinner="Predicting passes...")
def analyze(query_kind, query_value, station_fields, start, hours, min_elevation, max_satellites):
    tracked, _skipped, _result = load_orbit_data(query_kind, query_value)
    station = Station(*station_fields)
    end = start + timedelta(hours=hours)
 
    chosen = sorted(tracked, key=lambda item: item.name)[:max_satellites]
    passes, ages = [], {}
    for item in chosen:
        ages[item.norad_id] = epoch_age_days(item, start)
        passes.extend(find_passes(item, station, start, end, min_elevation))
    passes.sort(key=lambda p: p.start)
    return Analysis(tuple(passes), ages, len(chosen))
 
 
def fmt_time(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S")
 
 
def fmt_duration(seconds):
    minutes, secs = divmod(int(round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {secs:02d}s"
 
 
# --- sidebar: all inputs live in a form so nothing is downloaded until submitted ---
 
st.title("🛰️ Satellite Pass & Contact Planner")
st.caption(
    "Predicts passes over a ground station from public CelesTrak orbit data. "
    "Portfolio prototype, not an operational planning tool."
)
 
now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
 
with st.sidebar.form("planner"):
    kind_label = st.selectbox("Find satellites by", list(QUERY_KINDS))
    query_value = st.text_input(
        "Value",
        value="planet",
        help="A CelesTrak group name, part of a satellite name, or a catalog number.",
    )
    station_choice = st.selectbox("Ground station", [*PRESETS, CUSTOM_STATION])
    custom_lat = st.number_input("Custom latitude (°)", -90.0, 90.0, 0.0, format="%.4f")
    custom_lon = st.number_input("Custom longitude (°)", -180.0, 180.0, 0.0, format="%.4f")
    start_date = st.date_input("Start date (UTC)", value=now.date())
    start_clock = st.time_input("Start time (UTC)", value=time(now.hour, 0))
    hours = st.slider("Window (hours)", 1, 72, 24)
    min_elevation = st.slider("Minimum elevation (°)", 0, 60, 10)
    min_duration = st.slider("Minimum contact duration (seconds)", 0, 600, 60, step=10)
    max_satellites = st.slider("Max satellites", 1, 200, 25)
    submitted = st.form_submit_button("Compute passes")
 
if submitted:
    if station_choice == CUSTOM_STATION:
        station_fields = ("Custom", float(custom_lat), float(custom_lon), 0.0)
    else:
        site = PRESETS[station_choice]
        station_fields = (site.name, site.latitude_deg, site.longitude_deg, site.elevation_m)
    st.session_state["params"] = {
        "query_kind": QUERY_KINDS[kind_label],
        "query_value": query_value.strip(),
        "station_fields": station_fields,
        "start": datetime.combine(start_date, start_clock, tzinfo=timezone.utc),
        "hours": int(hours),
        "min_elevation": float(min_elevation),
        "min_duration": float(min_duration),
        "max_satellites": int(max_satellites),
    }
 
params = st.session_state.get("params")
if params is None:
    st.info("Choose a station and time window in the sidebar, then click **Compute passes**.")
    st.stop()
 
# --- load data ---
 
try:
    tracked, skipped, fetch = load_orbit_data(params["query_kind"], params["query_value"])
except (OrbitDataError, ValueError) as exc:
    st.error(f"Could not load orbit data: {exc}")
    st.stop()
 
if fetch.stale:
    st.warning("CelesTrak could not be reached, so a previously downloaded copy is being used.")
if skipped:
    with st.expander(f"{len(skipped)} satellites could not be loaded"):
        for name, reason in skipped:
            st.write(f"{name}: {reason}")
 
start = params["start"]
end = start + timedelta(hours=params["hours"])
station = Station(*params["station_fields"])
 
analysis = analyze(
    params["query_kind"],
    params["query_value"],
    params["station_fields"],
    start,
    params["hours"],
    params["min_elevation"],
    params["max_satellites"],
)
 
if len(tracked) > analysis.satellites_used:
    st.caption(
        f"Showing the first {analysis.satellites_used} of {len(tracked)} satellites "
        "(alphabetically). Raise 'Max satellites' to include more; it takes longer."
    )
 
stale = sum(1 for age in analysis.epoch_ages.values() if age > STALE_EPOCH_DAYS)
if stale:
    st.warning(
        f"{stale} satellites have orbit data more than {STALE_EPOCH_DAYS:.0f} days from the "
        "start time, so their predictions may be inaccurate."
    )
 
passes = filter_passes(
    analysis.passes,
    min_elevation_deg=params["min_elevation"],
    min_duration_s=params["min_duration"],
)
 
# --- summary ---
 
st.subheader(f"Contacts over {station.name}")
st.caption(f"{fmt_time(start)} to {fmt_time(end)} UTC, minimum elevation {params['min_elevation']:.0f}°")
 
windows = contact_windows(passes)
coverage = coverage_summary(windows, start, end)
 
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Satellites", analysis.satellites_used)
c2.metric("Passes", len(passes))
c3.metric("Distinct contact windows", coverage.contact_count)
c4.metric("Time in view", f"{coverage.coverage_fraction:.0%}")
c5.metric("Longest gap", fmt_duration(coverage.longest_gap_seconds))
 
if not passes:
    st.info("No passes meet these settings. Try a longer window or a lower minimum elevation.")
    st.stop()
 
# --- timeline ---
 
st.subheader("Contact timeline")
timeline = pd.DataFrame(
    {
        "Satellite": [p.satellite for p in passes],
        "Start": [p.start.replace(tzinfo=None) for p in passes],
        "Finish": [p.end.replace(tzinfo=None) for p in passes],
    }
)
timeline_fig = px.timeline(timeline, x_start="Start", x_end="Finish", y="Satellite")
timeline_fig.update_yaxes(autorange="reversed")
timeline_fig.update_layout(height=160 + 22 * timeline["Satellite"].nunique())
st.plotly_chart(timeline_fig, width="stretch")
 
# --- pass table ---
 
st.subheader("Pass list")
table = pd.DataFrame(
    {
        "Satellite": [p.satellite for p in passes],
        "NORAD ID": [p.norad_id for p in passes],
        "Rise (UTC)": [fmt_time(p.start) for p in passes],
        "Peak (UTC)": [fmt_time(p.peak) for p in passes],
        "Set (UTC)": [fmt_time(p.end) for p in passes],
        "Max elevation (°)": [round(p.max_elevation_deg, 1) for p in passes],
        "Duration (min)": [round(p.duration_s / 60.0, 1) for p in passes],
        "Rise azimuth (°)": [round(p.start_azimuth_deg, 0) for p in passes],
        "Set azimuth (°)": [round(p.end_azimuth_deg, 0) for p in passes],
    }
)
st.dataframe(table, width="stretch", hide_index=True)
st.download_button(
    "Download pass list (CSV)",
    data=table.to_csv(index=False).encode("utf-8"),
    file_name="passes.csv",
    mime="text/csv",
)
 
# --- ground track ---
 
st.subheader("Ground track")
names = sorted({p.satellite for p in passes})
chosen_name = st.selectbox("Satellite", names)
track_hours = st.slider("Hours to plot", 1, 12, 3)
 
item = next(t for t in tracked if t.name == chosen_name)
_times, lats, lons = ground_track(item, start, start + timedelta(hours=track_hours), step_s=30)
track_lats, track_lons = with_gaps(lats, lons)
 
map_fig = go.Figure()
map_fig.add_trace(
    go.Scattergeo(lat=track_lats, lon=track_lons, mode="lines", name=chosen_name)
)
map_fig.add_trace(
    go.Scattergeo(
        lat=[station.latitude_deg],
        lon=[station.longitude_deg],
        mode="markers",
        name=station.name,
        marker={"size": 9, "symbol": "diamond", "color": "red"},
    )
)
map_fig.update_geos(projection_type="natural earth", showland=True, showcountries=True)
map_fig.update_layout(height=450, margin={"l": 0, "r": 0, "t": 10, "b": 0})
st.plotly_chart(map_fig, width="stretch")
 
st.caption(
    "Predictions use SGP4 with publicly available orbit data. Accuracy is limited and "
    "degrades with the age of the data. Not for operational use."
)