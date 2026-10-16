"""Phase 0: OurAirports CSV (airports.csv, runways.csv), no key.

Checks: download size/latency, fields, IATA -> ICAO mapping (ANC -> PANC), US state for region filters,
and the effective-runway count (A-15: open AND >= 5,000 ft) for the airports in the four questions.
"""

import io

import httpx
import pandas as pd

from _common import UA, Timer, save

BASE = "https://davidmegginson.github.io/ourairports-data"
MIN_FT = 5000  # A-15 (config.yaml runways.effective_min_length_ft)
CHECK = ["SNA", "SFO", "LAX", "BOS", "ANC", "PVD", "BDL", "PWM", "MHT", "BTV", "LGA", "DCA", "EWR"]


def get_csv(client: httpx.Client, name: str) -> tuple[pd.DataFrame, float, int]:
    with Timer() as t:
        r = client.get(f"{BASE}/{name}")
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content), keep_default_na=False, low_memory=False), t.seconds, len(r.content)


def main() -> None:
    result = {"source": "OurAirports"}
    with httpx.Client(timeout=120, headers=UA, follow_redirects=True) as client:
        airports, s1, b1 = get_csv(client, "airports.csv")
        runways, s2, b2 = get_csv(client, "runways.csv")
    result["airports_csv"] = {"seconds": s1, "mb": round(b1 / 1e6, 1), "rows": len(airports),
                              "columns": list(airports.columns)}
    result["runways_csv"] = {"seconds": s2, "mb": round(b2 / 1e6, 1), "rows": len(runways),
                             "columns": list(runways.columns)}

    us = airports[(airports["iso_country"] == "US") & (airports["iata_code"] != "")]
    sample = {}
    for code in CHECK:
        a = us[us["iata_code"] == code]
        if a.empty:
            sample[code] = "not found"
            continue
        a = a.iloc[0]
        rw = runways[runways["airport_ident"] == a["ident"]].copy()
        rw["length_ft"] = pd.to_numeric(rw["length_ft"], errors="coerce")
        effective = rw[(rw["closed"].astype(str) != "1") & (rw["length_ft"] >= MIN_FT)]
        sample[code] = {
            "icao": a["icao_code"] or a["ident"],
            "state": a["iso_region"].removeprefix("US-"),
            "type": a["type"],
            "runways_raw": len(rw),
            "runways_effective": len(effective),
            "runways": [f"{r.le_ident}/{r.he_ident} {int(r.length_ft) if pd.notna(r.length_ft) else '?'}ft"
                        f"{' CLOSED' if str(r.closed) == '1' else ''}" for r in rw.itertuples()],
        }
    result["sample"] = sample
    result["us_airports_with_iata"] = len(us)
    result["works"] = True
    save("ourairports", result)


if __name__ == "__main__":
    main()
