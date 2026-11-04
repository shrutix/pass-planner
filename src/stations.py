"""Ground station definitions (plain Python)."""
 
from dataclasses import dataclass
 
 
@dataclass(frozen=True)
class Station:
    name: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: float = 0.0
 
    def __post_init__(self):
        # Written so that NaN also fails
        if not -90.0 <= self.latitude_deg <= 90.0:
            raise ValueError(f"Latitude must be within [-90, 90], got {self.latitude_deg}")
        if not -180.0 <= self.longitude_deg <= 180.0:
            raise ValueError(f"Longitude must be within [-180, 180], got {self.longitude_deg}")
 
 
# Approximate coordinates of example sites. These are not the locations of any operator's real ground stations
PRESETS = {
    "San Francisco, USA (example)": Station("San Francisco", 37.7749, -122.4194, 16.0),
    "Fairbanks, USA (example)": Station("Fairbanks", 64.8378, -147.7164, 136.0),
    "Svalbard, Norway (example)": Station("Svalbard", 78.2298, 15.3900, 0.0),
    "Punta Arenas, Chile (example)": Station("Punta Arenas", -53.1638, -70.9171, 0.0),
    "Berlin, Germany (example)": Station("Berlin", 52.5200, 13.4050, 34.0),
}