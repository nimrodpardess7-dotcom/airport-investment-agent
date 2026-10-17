"""OurAirports CSV (airports.csv, runways.csv). No key.

Used for: IATA <-> ICAO codes, state (region filters), coordinates (OpenSky distances), and the
effective-runway count (A-15: open AND >= the minimum length in config).
"""

import io

import httpx
import pandas as pd

from config import CONFIG
from sources.cache import cached, ttl

BASE = "https://davidmegginson.github.io/ourairports-data"


def _csv(name: str) -> pd.DataFrame:
    def fetch() -> bytes:
        r = httpx.get(f"{BASE}/{name}", timeout=120, follow_redirects=True)
        r.raise_for_status()
        return r.content

    return pd.read_csv(io.BytesIO(cached(f"ourairports/{name}", ttl("ourairports"), fetch)),
                       keep_default_na=False, low_memory=False)


def airports() -> pd.DataFrame:
    """U.S. airports with an IATA code, indexed by IATA: name, ident, icao, state, lat, lon, runways."""
    a = _csv("airports.csv")
    a = a[(a["iso_country"] == "US") & (a["iata_code"] != "")].drop_duplicates("iata_code")
    out = pd.DataFrame({
        "name": a["name"].values,
        "ident": a["ident"].values,
        "icao": a["icao_code"].where(a["icao_code"] != "", a["ident"]).values,
        "state": a["iso_region"].str.removeprefix("US-").values,
        "lat": a["latitude_deg"].astype(float).values,
        "lon": a["longitude_deg"].astype(float).values,
    }, index=pd.Index(a["iata_code"].values, name="airport"))
    out["runways"] = out["ident"].map(_effective_runways_by_ident()).fillna(0).astype(int)
    return out


def _effective_runways_by_ident() -> pd.Series:
    """A-15: count runways that are open and at least the configured length."""
    min_ft = CONFIG["runways"]["effective_min_length_ft"]
    rw = _csv("runways.csv")
    length = pd.to_numeric(rw["length_ft"], errors="coerce")
    ok = rw[(rw["closed"].astype(str) != "1") & (length >= min_ft)]
    return ok.groupby("airport_ident").size()


def coordinates() -> pd.DataFrame:
    """Every airport worldwide indexed by ident (ICAO for most), with lat/lon. For OpenSky destinations."""
    a = _csv("airports.csv")
    return a.set_index("ident")[["latitude_deg", "longitude_deg"]].astype(float).rename(
        columns={"latitude_deg": "lat", "longitude_deg": "lon"})
