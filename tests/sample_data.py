"""Illustrative orbit data for tests.
 
These element sets are made up to resemble real orbits (one ISS-like, one
polar). They are NOT real catalog data, and NORAD IDs 99001 and 123456 are
not real satellites.
"""
 
COLUMNS = [
    "OBJECT_NAME",
    "OBJECT_ID",
    "EPOCH",
    "MEAN_MOTION",
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "EPHEMERIS_TYPE",
    "CLASSIFICATION_TYPE",
    "NORAD_CAT_ID",
    "ELEMENT_SET_NO",
    "REV_AT_EPOCH",
    "BSTAR",
    "MEAN_MOTION_DOT",
    "MEAN_MOTION_DDOT",
]
 
ISS_LIKE = {
    "OBJECT_NAME": "SAMPLE ISS-LIKE",
    "OBJECT_ID": "1998-067A",
    "EPOCH": "2026-10-30T00:00:00.000000",
    "MEAN_MOTION": "15.50000000",
    "ECCENTRICITY": "0.00050000",
    "INCLINATION": "51.6400",
    "RA_OF_ASC_NODE": "100.0000",
    "ARG_OF_PERICENTER": "100.0000",
    "MEAN_ANOMALY": "260.0000",
    "EPHEMERIS_TYPE": "0",
    "CLASSIFICATION_TYPE": "U",
    "NORAD_CAT_ID": "99001",
    "ELEMENT_SET_NO": "999",
    "REV_AT_EPOCH": "50000",
    "BSTAR": "0.00010000",
    "MEAN_MOTION_DOT": "0.00010000",
    "MEAN_MOTION_DDOT": "0",
}
 
POLAR = {
    **ISS_LIKE,
    "OBJECT_NAME": "SAMPLE POLAR",
    "OBJECT_ID": "2026-001A",
    "MEAN_MOTION": "15.20000000",
    "ECCENTRICITY": "0.00100000",
    "INCLINATION": "97.5000",
    "RA_OF_ASC_NODE": "40.0000",
    "NORAD_CAT_ID": "123456",  # six digits: fine in OMM, impossible in a TLE
}
 
EPOCH_UTC = (2026, 10, 30)  # year, month, day of the sample epoch (00:00 UTC)
 
 
def csv_text(*rows):
    lines = [",".join(COLUMNS)]
    for row in rows:
        lines.append(",".join(row[column] for column in COLUMNS))
    return "\n".join(lines) + "\n"
 
 
SAMPLE_CSV = csv_text(ISS_LIKE, POLAR)