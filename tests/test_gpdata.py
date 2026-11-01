import os
 
import pytest
 
from gpdata import (
    FetchResult,
    OrbitDataError,
    build_query_url,
    fetch_gp_csv,
    parse_omm_csv,
)
from sample_data import SAMPLE_CSV, csv_text, ISS_LIKE, POLAR
 
NOW = 1_800_000_000.0
URL = build_query_url(group="planet")
 
 
# --- query URLs ---
 
def test_group_url_asks_for_csv():
    url = build_query_url(group="planet")
    assert url.startswith("https://celestrak.org/NORAD/elements/gp.php?")
    assert "GROUP=planet" in url and "FORMAT=csv" in url
 
 
def test_name_is_url_encoded():
    assert "NAME=SKYSAT+C1" in build_query_url(name="SKYSAT C1")
 
 
def test_catalog_number_url():
    assert "CATNR=25544" in build_query_url(catnr="25544")
    assert "CATNR=123456" in build_query_url(catnr=123456)
 
 
@pytest.mark.parametrize("bad", ["", "abc", "12 34", "1234567890", "-5"])
def test_bad_catalog_number_is_rejected(bad):
    with pytest.raises(ValueError):
        build_query_url(catnr=bad)
 
 
def test_exactly_one_selector_is_required():
    with pytest.raises(ValueError):
        build_query_url()
    with pytest.raises(ValueError):
        build_query_url(group="planet", name="SKYSAT")
 
 
def test_whitespace_around_a_value_is_ignored():
    assert build_query_url(group="  planet  ") == build_query_url(group="planet")
 
 
# --- parsing ---
def test_parses_valid_csv_into_row_dicts():
    rows = parse_omm_csv(SAMPLE_CSV)
    assert [r["OBJECT_NAME"] for r in rows] == ["SAMPLE ISS-LIKE", "SAMPLE POLAR"]
    assert rows[0]["INCLINATION"] == "51.6400"
 
 
def test_six_digit_catalog_numbers_pass_through_unchanged():
    assert parse_omm_csv(SAMPLE_CSV)[1]["NORAD_CAT_ID"] == "123456"
 
 
def test_byte_order_mark_is_tolerated():
    assert len(parse_omm_csv("﻿" + SAMPLE_CSV)) == 2
 
 
def test_blank_lines_are_ignored():
    assert len(parse_omm_csv(SAMPLE_CSV + "\n\n,,,\n")) == 2
 
 
@pytest.mark.parametrize("text", ["", "   \n", None])
def test_empty_response_raises(text):
    with pytest.raises(OrbitDataError, match="empty"):
        parse_omm_csv(text)
 
 
def test_error_text_from_the_server_is_reported_clearly():
    with pytest.raises(OrbitDataError, match="No GP data found"):
        parse_omm_csv("No GP data found")
 
 
def test_missing_columns_are_named():
    header_only_missing_bstar = SAMPLE_CSV.replace("BSTAR", "BSTAR_RENAMED", 1)
    with pytest.raises(OrbitDataError, match="BSTAR"):
        parse_omm_csv(header_only_missing_bstar)
 
 
def test_header_with_no_rows_raises():
    with pytest.raises(OrbitDataError, match="no satellites"):
        parse_omm_csv(csv_text())
 
 
# --- caching ---
 
class Fetcher:
    def __init__(self, text=SAMPLE_CSV, error=None):
        self.text, self.error, self.calls = text, error, 0
 
    def __call__(self, url):
        self.calls += 1
        if self.error:
            raise self.error
        return self.text
 
 
def seed_cache(tmp_path, age_hours, text=csv_text(ISS_LIKE)):
    """Create a cached copy for URL that is age_hours old at time NOW."""
    from gpdata import _cache_path
 
    path = _cache_path(tmp_path, URL)
    path.write_text(text, encoding="utf-8")
    mtime = NOW - age_hours * 3600
    os.utime(path, (mtime, mtime))
    return path
 
 
def fetch(tmp_path, fetcher, **kwargs):
    return fetch_gp_csv(URL, tmp_path, fetcher=fetcher, clock=lambda: NOW, **kwargs)
 
 
def test_first_fetch_downloads_and_writes_the_cache(tmp_path):
    fetcher = Fetcher()
    result = fetch(tmp_path, fetcher)
    assert isinstance(result, FetchResult)
    assert (result.from_cache, result.stale, result.text) == (False, False, SAMPLE_CSV)
    assert fetcher.calls == 1
    assert len(list(tmp_path.glob("gp_*.csv"))) == 1
 
 
def test_fresh_cache_is_used_without_any_request(tmp_path):
    seed_cache(tmp_path, age_hours=1)
    fetcher = Fetcher()
    result = fetch(tmp_path, fetcher, max_age_hours=6)
    assert (result.from_cache, result.stale) == (True, False)
    assert fetcher.calls == 0
 
 
def test_old_cache_is_refreshed(tmp_path):
    path = seed_cache(tmp_path, age_hours=7)
    fetcher = Fetcher()
    result = fetch(tmp_path, fetcher, max_age_hours=6)
    assert (result.from_cache, result.stale) == (False, False)
    assert fetcher.calls == 1
    assert path.read_text(encoding="utf-8") == SAMPLE_CSV
    assert path.stat().st_mtime == NOW
 
 
def test_network_failure_falls_back_to_the_old_copy(tmp_path):
    old = csv_text(ISS_LIKE)
    seed_cache(tmp_path, age_hours=7, text=old)
    result = fetch(tmp_path, Fetcher(error=OrbitDataError("offline")), max_age_hours=6)
    assert (result.from_cache, result.stale, result.text) == (True, True, old)
 
 
def test_network_failure_with_no_cache_raises(tmp_path):
    with pytest.raises(OrbitDataError, match="offline"):
        fetch(tmp_path, Fetcher(error=OrbitDataError("offline")))
 
 
def test_invalid_response_never_overwrites_good_cache(tmp_path):
    old = csv_text(ISS_LIKE)
    path = seed_cache(tmp_path, age_hours=7, text=old)
    result = fetch(tmp_path, Fetcher(text="No GP data found"), max_age_hours=6)
    assert result.stale and result.text == old
    assert path.read_text(encoding="utf-8") == old
 
 
def test_invalid_response_with_no_cache_raises_and_writes_nothing(tmp_path):
    with pytest.raises(OrbitDataError):
        fetch(tmp_path, Fetcher(text="No GP data found"))
    assert list(tmp_path.glob("gp_*.csv")) == []
 
 
def test_each_query_has_its_own_cache_file(tmp_path):
    fetch_gp_csv(build_query_url(group="a"), tmp_path, fetcher=Fetcher(), clock=lambda: NOW)
    fetch_gp_csv(build_query_url(group="b"), tmp_path, fetcher=Fetcher(), clock=lambda: NOW)
    assert len(list(tmp_path.glob("gp_*.csv"))) == 2
 
 
def test_cache_directory_is_created_if_missing(tmp_path):
    target = tmp_path / "nested" / "cache"
    fetch_gp_csv(URL, target, fetcher=Fetcher(), clock=lambda: NOW)
    assert target.is_dir()
 
 
def test_rows_from_a_cached_copy_are_parseable(tmp_path):
    seed_cache(tmp_path, age_hours=1, text=csv_text(POLAR))
    rows = parse_omm_csv(fetch(tmp_path, Fetcher()).text)
    assert rows[0]["OBJECT_NAME"] == "SAMPLE POLAR"