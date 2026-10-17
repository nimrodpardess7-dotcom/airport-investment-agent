"""Bureau of Transportation Statistics (BTS). No API keys.

Three feeds, each with one job (decisions D1-D3 in docs/phase0_findings.md):

1. Socrata T-100 Segment Summary by Origin Airport (r495-tyji): powers the score.
   One row per airport per month. Freighters are mixed into departures.
2. TranStats T-100 Segment, All Carriers (table FMG): route x carrier x aircraft config.
   Used for route mix (exact passenger/cargo split), ULCC share and the cargo-heavy flag.
3. TranStats delay causes: NAS delay share for the Airfield rule (reporting airlines only).
"""

import hashlib
import io
import json
import re
import zipfile

import httpx
import pandas as pd

from config import CONFIG
from sources.cache import cached, ttl

SRC = CONFIG["sources"]
HEADERS = {"User-Agent": "airport-investment-agent"}
TIMEOUT = 600


# --- 1. Socrata T-100 summary -------------------------------------------------------------------

def _soql(params: dict) -> list[dict]:
    url = f"{SRC['bts_base_url']}/{SRC['bts_t100_dataset']}.json"
    # Cache key = hash of the full query, so different windows never share a file.
    key = "bts/" + hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16] + ".json"

    def fetch() -> bytes:
        r = httpx.get(url, params={f"${k}": v for k, v in params.items()}, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.content

    return json.loads(cached(key, ttl("bts_t100"), fetch))


def latest_month() -> str:
    """Latest published month in the summary, 'YYYY-MM'."""
    return _soql({"select": "max(reporting_month) as latest"})[0]["latest"][:7]


def monthly(start: str, end: str) -> pd.DataFrame:
    """Departures, passengers, seats per airport per month, for months start..end ('YYYY-MM').

    Aggregated server-side with SoQL, so we never pull millions of rows.
    """
    limit = 50000
    rows = _soql({
        "select": "origin_airport_code as airport, reporting_month as month, sum(total_departures) as departures, "
                  "sum(total_passengers) as passengers, sum(total_seats) as seats",
        "where": f"reporting_month between '{start}-01' and '{end}-01'",
        "group": "origin_airport_code, reporting_month",
        "limit": limit,
    })
    if len(rows) >= limit:
        raise RuntimeError("SoQL row limit reached; narrow the window")
    df = pd.DataFrame(rows)
    df["month"] = df["month"].str[:7]
    for c in ["departures", "passengers", "seats"]:
        df[c] = pd.to_numeric(df[c])
    return df


# --- 2. TranStats T-100 route level -------------------------------------------------------------

T100_FIELDS = ["YEAR", "MONTH", "UNIQUE_CARRIER", "ORIGIN", "DEST", "DEST_COUNTRY", "DISTANCE",
               "DEPARTURES_PERFORMED", "SEATS", "PASSENGERS", "AIRCRAFT_CONFIG"]
AIRCRAFT_CONFIG = {1: "passenger", 2: "freighter", 3: "combi", 4: "seaplane"}


def _hidden_fields(html: str) -> dict:
    return dict(re.findall(r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]+value="([^"]*)"', html))


def transtats_latest() -> str:
    """Latest month TranStats says is available, 'YYYY-MM'."""
    def fetch() -> bytes:
        return httpx.get(SRC["transtats_t100_form"], headers=HEADERS, timeout=TIMEOUT).content

    html = cached("transtats/form.html", ttl("transtats_t100"), fetch).decode("utf-8", "replace")
    m = re.search(r"Latest Available Data:\s*([A-Za-z]+)\s+(\d{4})", html)
    return pd.Timestamp(f"{m.group(1)} 1 {m.group(2)}").strftime("%Y-%m")


def segments(year: int, month: int | None = None) -> pd.DataFrame:
    """All T-100 segments for one year (month=None) or one month. One row per carrier x route x aircraft type.

    Adds `aircraft` (passenger / freighter / combi / seaplane) and `distance_km`.
    """
    period = "All" if month is None else str(month)

    def fetch() -> bytes:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
            data = _hidden_fields(client.get(SRC["transtats_t100_form"]).text)
            data.update({"cboGeography": "All", "cboYear": str(year), "cboPeriod": period,
                         "chkDownloadZip": "on", "btnDownload": "Download"})
            data.update({f: "on" for f in T100_FIELDS})
            r = client.post(SRC["transtats_t100_form"], data=data)
            r.raise_for_status()
            if not r.content.startswith(b"PK"):
                raise RuntimeError("TranStats did not return a zip")
            return r.content

    zf = zipfile.ZipFile(io.BytesIO(cached(f"transtats/t100_{year}_{period}.zip", ttl("transtats_t100"), fetch)))
    name = next(n for n in zf.namelist() if n.upper().startswith("T_"))
    df = pd.read_csv(zf.open(name), low_memory=False)
    df["aircraft"] = df["AIRCRAFT_CONFIG"].map(AIRCRAFT_CONFIG)
    df["distance_km"] = df["DISTANCE"] * 1.609344
    return df


# --- 3. TranStats delay causes ------------------------------------------------------------------

def delay_causes(months: int = 12) -> pd.DataFrame:
    """Delay causes per carrier x airport x month for the latest `months` months (reporting airlines only)."""
    base = SRC["transtats_delay_causes_form"].rsplit("/", 1)[0] + "/"

    def fetch() -> bytes:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
            page = client.get(SRC["transtats_delay_causes_form"]).text
            # Periods are coded year*12 + month; the first option of PeriodTo is the latest month.
            latest = int(re.search(r"name='PeriodTo'.*?value\s*=\s*'?(\d+)", page, re.S | re.I).group(1))
            page = client.post(SRC["transtats_delay_causes_form"], data={
                "Carrier": "All", "Airport": "All",
                "PeriodFrom": str(latest - months + 1), "PeriodTo": str(latest)}).text
            href = re.search(r"href='(ot_delaycause1_DL\.aspx[^']+)'", page, re.I).group(1)
            r = client.get(base + href)
            r.raise_for_status()
            return r.content

    zf = zipfile.ZipFile(io.BytesIO(cached(f"transtats/delay_causes_{months}m.zip", ttl("transtats_delay_causes"), fetch)))
    df = pd.read_csv(zf.open(zf.namelist()[0]))
    df.columns = [c.strip() for c in df.columns]
    df["month"] = df["year"].astype(int).astype(str) + "-" + df["month"].astype(int).map("{:02d}".format)
    return df
