"""Download, cache, and validate satellite orbit data from CelesTrak.
 
Uses the OMM CSV format rather than TLEs. CelesTrak is running out of 5-digit
catalog numbers, and objects cataloged after that point cannot be expressed as
TLEs, while OMM (CSV/JSON/XML) has no such limit.
 
This module is plain Python with no Skyfield dependency.
 
Be a good citizen: CelesTrak asks clients not to repeat requests that fail with
HTTP 403/404 and may block abusive IP addresses. Downloads are cached on disk,
and a failed request is never retried automatically.
"""
 
import csv
import hashlib
import io
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
 
GP_ENDPOINT = "https://celestrak.org/NORAD/elements/gp.php"
 
# Conservative default: reuse a download for several hours before asking again.
DEFAULT_MAX_AGE_HOURS = 6.0
 
# Edit this to identify yourself (repo URL or email) before heavy use.
USER_AGENT = "orbit-pass-planner/0.1 (personal portfolio project)"
 
# The columns needed to build a satellite from OMM data.
REQUIRED_FIELDS = (
    "OBJECT_NAME",
    "NORAD_CAT_ID",
    "EPOCH",
    "MEAN_MOTION",
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "BSTAR",
    "MEAN_MOTION_DOT",
    "MEAN_MOTION_DDOT",
)
 
 
class OrbitDataError(RuntimeError):
    """Orbit data could not be downloaded or is not valid OMM CSV."""
 
 
@dataclass(frozen=True)
class FetchResult:
    text: str
    from_cache: bool
    stale: bool  # True when the download failed and an older cached copy was used
    fetched_at: float  # Unix time the text was downloaded
 
 
def build_query_url(group=None, catnr=None, name=None):
    """Build a CelesTrak GP query URL that returns OMM CSV.
 
    Give exactly one selector:
      group: a CelesTrak group name (check celestrak.org for the current list)
      catnr: a NORAD catalog number, 1 to 9 digits
      name:  part of a satellite name
    """
    selectors = {
        key: value
        for key, value in (("GROUP", group), ("CATNR", catnr), ("NAME", name))
        if value is not None and str(value).strip() != ""
    }
    if len(selectors) != 1:
        raise ValueError("Give exactly one of group, catnr, or name.")
 
    ((key, value),) = selectors.items()
    value = str(value).strip()
    if key == "CATNR" and not (value.isdigit() and 1 <= len(value) <= 9):
        raise ValueError("A catalog number must be 1 to 9 digits.")
 
    return f"{GP_ENDPOINT}?{urllib.parse.urlencode({key: value, 'FORMAT': 'csv'})}"
 
 
def parse_omm_csv(text):
    """Parse OMM CSV into a list of row dicts, validating the columns.
 
    CelesTrak answers a bad query with a short plain-text message instead of
    CSV, so a missing-column error includes the start of the response.
    """
    text = (text or "").lstrip("﻿").strip()
    if not text:
        raise OrbitDataError("CelesTrak returned an empty response.")
 
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []
    missing = [name for name in REQUIRED_FIELDS if name not in columns]
    if missing:
        snippet = " ".join(text[:120].split())
        raise OrbitDataError(
            f"The response is not OMM CSV (missing columns: {', '.join(missing)}). "
            f"Start of response: {snippet!r}"
        )
 
    rows = [row for row in reader if any((v or "").strip() for v in row.values())]
    if not rows:
        raise OrbitDataError("The response contained no satellites.")
    return rows
 
 
def _cache_path(cache_dir, url):
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return Path(cache_dir) / f"gp_{digest}.csv"
 
 
def http_fetch(url, timeout=30):
    """Download a URL once. Never retries."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # check before URLError, its parent
        raise OrbitDataError(
            f"CelesTrak returned HTTP {exc.code}. Repeating the request will not "
            "change the answer, so check the query before trying again."
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OrbitDataError(f"Could not reach CelesTrak: {exc}") from exc
 
 
def fetch_gp_csv(
    url,
    cache_dir,
    max_age_hours=DEFAULT_MAX_AGE_HOURS,
    fetcher=http_fetch,
    clock=time.time,
):
    """Return OMM CSV for ``url``, using an on-disk cache.
 
    * A cached copy younger than ``max_age_hours`` is returned without any
      network request.
    * Otherwise the data is downloaded and validated before it replaces the
      cache, so a bad response can never overwrite good data.
    * If the download or validation fails and an older copy exists, the old
      copy is returned with ``stale=True``. With no cached copy the error is
      raised.
 
    ``fetcher`` and ``clock`` can be replaced in tests.
    """
    path = _cache_path(cache_dir, url)
    now = clock()
 
    cached_text = cached_at = None
    if path.exists():
        cached_text = path.read_text(encoding="utf-8")
        cached_at = path.stat().st_mtime
        if now - cached_at < max_age_hours * 3600:
            return FetchResult(cached_text, True, False, cached_at)
 
    try:
        text = fetcher(url)
        parse_omm_csv(text)  # validate before caching
    except OrbitDataError:
        if cached_text is not None:
            return FetchResult(cached_text, True, True, cached_at)
        raise
 
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (now, now))
    return FetchResult(text, False, False, now)