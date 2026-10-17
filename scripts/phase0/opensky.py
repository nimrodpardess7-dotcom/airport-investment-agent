"""Phase 0 checklist #4 and A-06a: OpenSky departures from ANC (ICAO PANC) over the last 7 days.

Auth: OAuth2 client credentials (OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET in .env).
Per the API docs, flight queries are limited to ~2 days per request, so 7 days = 4 chunked requests.
Checks: latency, fields, how many flights have a null estimated destination, the long-haul share
(> 4,000 km, A-05; 3,500 km sensitivity), and the callsign-prefix cargo split (A-06a) with the
list of unclassified callsign prefixes so they can be reviewed by hand.
If credentials are missing, the result is "pending credentials".
"""

import io
import math
import os
import time
from collections import Counter
from pathlib import Path

import httpx
import pandas as pd
import yaml
from dotenv import load_dotenv

from _common import ROOT, UA, Timer, save

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API = "https://opensky-network.org/api"
AIRPORT = "PANC"


def km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance (haversine), km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def main() -> None:
    load_dotenv(ROOT / ".env")
    cid, secret = os.getenv("OPENSKY_CLIENT_ID"), os.getenv("OPENSKY_CLIENT_SECRET")
    result = {"source": "OpenSky Network /flights/departure", "airport": AIRPORT}
    if not cid or not secret:
        result.update(works=None, status="pending credentials (.env missing OPENSKY_CLIENT_ID/SECRET)")
        return save("opensky", result)

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    # The Phase 0 callsign list (old A-06a), kept here only to reproduce the test; removed from config by D2.
    cargo_prefixes = {"FDX", "UPS", "GTI", "PAC", "CKS", "ABX", "ATN", "WGN", "CLX", "NCA", "CKK", "CAO",
                      "CSS", "NAC", "LYC"}
    long_km, alt_km = config["route_mix"]["long_haul_km"], config["route_mix"]["long_haul_km_sensitivity"]

    with httpx.Client(timeout=120, headers=UA) as client:
        with Timer() as t:
            tok = client.post(TOKEN_URL, data={"grant_type": "client_credentials",
                                               "client_id": cid, "client_secret": secret})
        tok.raise_for_status()
        result["token_seconds"] = t.seconds
        headers = {"Authorization": f"Bearer {tok.json()['access_token']}"}

        # Flights are batch-processed overnight, so end yesterday. The API caps each request at ~2 days,
        # so a 7-day window is fetched as 2-day chunks.
        end = int(time.time()) // 86400 * 86400 - 86400
        begin = end - 7 * 86400
        rows, chunks = [], []
        for start in range(begin, end, 2 * 86400):
            stop = min(start + 2 * 86400, end)
            with Timer() as t:
                r = client.get(f"{API}/flights/departure", params={"airport": AIRPORT, "begin": start, "end": stop},
                               headers=headers)
            chunks.append({"status": r.status_code, "seconds": t.seconds, "bytes": len(r.content),
                           "credits_left": r.headers.get("X-Rate-Limit-Remaining")})
            if r.status_code == 200:
                rows += r.json()
            elif r.status_code != 404:  # 404 = no flights in that chunk
                result.update(works=False, chunks=chunks, body=r.text[:500])
                return save("opensky", result)
        result.update(chunks=chunks,
                      window_utc=[pd.Timestamp(begin, unit="s").isoformat(), pd.Timestamp(end, unit="s").isoformat()])
        flights = pd.DataFrame(rows)

        ap = pd.read_csv(io.BytesIO(client.get(
            "https://davidmegginson.github.io/ourairports-data/airports.csv").content),
            keep_default_na=False, low_memory=False).set_index("ident")

    result["fields"] = list(flights.columns)
    result["flights"] = len(flights)
    flights["callsign"] = flights["callsign"].fillna("").str.strip()
    flights["prefix"] = flights["callsign"].str[:3]
    flights["is_cargo"] = flights["prefix"].isin(cargo_prefixes)
    null_dest = flights["estArrivalAirport"].isna() | (flights["estArrivalAirport"] == "")
    result["null_destination"] = int(null_dest.sum())

    o = ap.loc[AIRPORT]
    def dist(icao):
        return km(o.latitude_deg, o.longitude_deg, ap.loc[icao].latitude_deg, ap.loc[icao].longitude_deg) \
            if icao in ap.index else None
    flights["km"] = flights["estArrivalAirport"].map(lambda c: dist(c) if c else None)
    known = flights[flights["km"].notna()]

    def share(df, thr):
        return round(float((df["km"] > thr).mean()), 3) if len(df) else None

    result["long_haul_share"] = {
        "all_known_dest": {str(long_km): share(known, long_km), str(alt_km): share(known, alt_km)},
        "passenger_only": {str(long_km): share(known[~known.is_cargo], long_km),
                           str(alt_km): share(known[~known.is_cargo], alt_km)},
        "flights_with_known_destination": len(known),
    }
    result["cargo_by_prefix"] = int(flights["is_cargo"].sum())
    result["top_prefixes_not_on_cargo_list"] = dict(Counter(flights.loc[~flights.is_cargo, "prefix"]).most_common(25))
    result["works"] = True
    save("opensky", result)


if __name__ == "__main__":
    main()
