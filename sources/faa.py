"""FAA NAS Status (nasstatus.faa.gov). No key.

/api/airport-events lists only airports with an active event (delay program, ground stop, closure,
NOTAM). "Not listed" means "no active event", not an error. The arrival rate and runway configuration
appear only for listed airports.
"""

import json

import httpx

from config import CONFIG
from sources.cache import cached, ttl

URL = CONFIG["sources"]["faa_nas_base_url"] + "/api/airport-events"


def _events() -> list[dict]:
    def fetch() -> bytes:
        r = httpx.get(URL, timeout=60)
        r.raise_for_status()
        return r.content

    return json.loads(cached("faa/airport_events.json", ttl("faa_nas_status"), fetch))


def status(airport: str) -> dict:
    """Live status for one IATA code: listed flag, GDP, ground stop, delays, arrival rate, runway config."""
    e = next((x for x in _events() if x["airportId"] == airport), None)
    if e is None:
        return {"airport": airport, "listed": False, "ground_delay": None, "ground_stop": None,
                "arrival_delay": None, "departure_delay": None, "arrival_rate": None, "runway_config": None}
    gdp, cfg = e.get("groundDelay"), e.get("airportConfig") or {}
    return {
        "airport": airport,
        "listed": True,
        "ground_delay": gdp and {"avg_minutes": gdp.get("avgDelay"), "max_minutes": gdp.get("maxDelay"),
                                 "reason": gdp.get("impactingCondition")},
        "ground_stop": e.get("groundStop"),
        "arrival_delay": e.get("arrivalDelay"),
        "departure_delay": e.get("departureDelay"),
        "arrival_rate": cfg.get("arrivalRate"),
        "runway_config": cfg and {"arrivals": cfg.get("arrivalRunwayConfig"),
                                  "departures": cfg.get("departureRunwayConfig")},
        "as_of": cfg.get("sourceTimeStamp") or (gdp or {}).get("updatedAt"),
    }
