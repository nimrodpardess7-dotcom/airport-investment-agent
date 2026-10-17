"""OpenSky Network REST client, for "last 7 days" questions only.

OAuth2 client credentials from .env. Flights are batch-processed overnight, so the window ends at
00:00 UTC yesterday. The API allows ~2 days per request, so the window is fetched in chunks.
No aircraft type is returned, so OpenSky answers report all flights with no passenger/cargo split (D2).
"""

import json
import os
import time

import httpx
import pandas as pd
from dotenv import load_dotenv

from config import CONFIG, ROOT
from sources.cache import cached, ttl

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API = "https://opensky-network.org/api/flights/departure"
DAY = 86400


def _token() -> str:
    load_dotenv(ROOT / ".env")
    r = httpx.post(TOKEN_URL, timeout=60, data={
        "grant_type": "client_credentials",
        "client_id": os.environ["OPENSKY_CLIENT_ID"],
        "client_secret": os.environ["OPENSKY_CLIENT_SECRET"],
    })
    r.raise_for_status()
    return r.json()["access_token"]


def departures(icao: str) -> tuple[pd.DataFrame, str, str]:
    """Departures from `icao` over the configured window. Returns (flights, window_start, window_end) in UTC."""
    days = CONFIG["sources"]["opensky_window_days"]
    step = CONFIG["sources"]["opensky_max_request_days"] * DAY
    end = int(time.time()) // DAY * DAY - DAY
    begin = end - days * DAY

    def fetch() -> bytes:
        headers = {"Authorization": f"Bearer {_token()}"}
        rows = []
        for start in range(begin, end, step):
            r = httpx.get(API, params={"airport": icao, "begin": start, "end": min(start + step, end)},
                          headers=headers, timeout=120)
            if r.status_code == 404:  # no flights in this chunk
                continue
            r.raise_for_status()
            rows += r.json()
        return json.dumps(rows).encode()

    flights = pd.DataFrame(json.loads(cached(f"opensky/{icao}_{begin}_{end}.json", ttl("opensky"), fetch)))
    fmt = "%Y-%m-%d"
    return flights, time.strftime(fmt, time.gmtime(begin)), time.strftime(fmt, time.gmtime(end - DAY))
