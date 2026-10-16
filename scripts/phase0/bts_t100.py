"""Phase 0 checklist #3 (and #6): BTS T-100 Segment Summary by Origin Airport (Socrata r495-tyji).

Checks: schema, publication lag (latest month), month completeness, server-side SoQL aggregation
latency and size, and a sanity read of the latest-12-months vs 2019 numbers for the four questions' airports.
"""

import httpx

from _common import UA, Timer, save

BASE = "https://data.bts.gov"
DS = "r495-tyji"
AIRPORTS = ["BOS", "PVD", "BDL", "PWM", "MHT", "BTV", "LAX", "SNA", "SFO", "ANC"]


def soql(client: httpx.Client, **params) -> tuple[list, float, int]:
    with Timer() as t:
        r = client.get(f"{BASE}/resource/{DS}.json", params={f"${k}": v for k, v in params.items()})
    r.raise_for_status()
    return r.json(), t.seconds, len(r.content)


def main() -> None:
    result = {"source": f"BTS T-100 Segment Summary by Origin Airport ({DS})"}
    with httpx.Client(timeout=120, headers=UA) as client:
        meta = client.get(f"{BASE}/api/views/{DS}.json").json()
        result["columns"] = [c["fieldName"] for c in meta["columns"]]
        result["has_carrier_column"] = any("carrier" in c for c in result["columns"])

        rows, s, _ = soql(client, select="max(reporting_month) as latest, min(reporting_month) as first")
        result["latest_month"], result["first_month"] = rows[0]["latest"][:7], rows[0]["first"][:7]
        result["latency_s"] = {"max_month": s}

        # Months published per year (national) -> completeness of the latest year.
        rows, s, _ = soql(client, select="year, count(distinct reporting_month) as months", group="year",
                          order="year")
        result["months_per_year"] = {r["year"]: int(r["months"]) for r in rows}
        result["latency_s"]["months_per_year"] = s

        # Server-side aggregation for every airport, one year: the query the scorer will run.
        rows, s, size = soql(client,
                             select="origin_airport_code, sum(total_departures) as dep, "
                                    "sum(total_passengers) as pax, sum(total_seats) as seats",
                             where="year='2019'", group="origin_airport_code", limit=50000)
        result["all_airports_one_year"] = {"airports": len(rows), "seconds": s, "bytes": size}

        # Latest 12 published months per airport (rolling window).
        latest = result["latest_month"]
        y, m = int(latest[:4]), int(latest[5:7])
        start = f"{y - 1}-{m + 1:02d}-01" if m < 12 else f"{y}-01-01"
        result["latest_12m_window"] = f"{start[:7]} .. {latest}"
        codes = ",".join(f"'{c}'" for c in AIRPORTS)
        sel = ("origin_airport_code, sum(total_departures) as dep, sum(total_passengers) as pax, "
               "sum(total_seats) as seats, sum(total_freight_lbs) as freight, "
               "count(distinct reporting_month) as months")
        l12, s1, _ = soql(client, select=sel, where=f"origin_airport_code in ({codes}) and reporting_month >= '{start}'",
                          group="origin_airport_code", limit=100)
        base, s2, _ = soql(client, select=sel, where=f"origin_airport_code in ({codes}) and year='2019'",
                           group="origin_airport_code", limit=100)
        result["latency_s"]["sample_latest12"] = s1
        result["latency_s"]["sample_2019"] = s2

        def f(r, k):
            return float(r.get(k, 0) or 0)

        b = {r["origin_airport_code"]: r for r in base}
        sample = {}
        for r in sorted(l12, key=lambda r: -f(r, "pax")):
            c, r0 = r["origin_airport_code"], b.get(r["origin_airport_code"], {})
            sample[c] = {
                "months_latest12": int(r["months"]),
                "pax_latest12": int(f(r, "pax")),
                "pax_2019": int(f(r0, "pax")),
                "load_factor_latest12": round(f(r, "pax") / f(r, "seats"), 3) if f(r, "seats") else None,
                "seats_per_dep_latest12": round(f(r, "seats") / f(r, "dep"), 1) if f(r, "dep") else None,
                "seats_per_dep_2019": round(f(r0, "seats") / f(r0, "dep"), 1) if f(r0, "dep") else None,
                "departures_latest12": int(f(r, "dep")),
                "departures_2019": int(f(r0, "dep")),
            }
        result["sample"] = sample

        # Do zero-seat (all-cargo) departures sit inside total_departures? Compare ANC freight vs seats.
        result["note_cargo_in_departures"] = (
            "total_departures includes all-cargo flights (no carrier/aircraft-config column), so "
            "seats per departure is diluted at cargo hubs (ANC, MEM, SDF). Compare ANC seats_per_dep."
        )
    result["works"] = True
    save("bts_t100", result)


if __name__ == "__main__":
    main()
