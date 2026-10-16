"""Phase 0 checklist #1 and #6: can code fetch TranStats T-100 route-level data at runtime?

Table FMG = "T-100 Segment (All Carriers)": origin x destination x carrier x aircraft config, monthly.
The download page is an ASP.NET form; we replay its postback with the fields we need and measure
size and latency for one month and for one full year.

Usage: python scripts/phase0/transtats_t100_route.py [year] [month|all]
"""

import io
import re
import sys
import zipfile

import httpx
import pandas as pd

from _common import OUT, UA, Timer, save

URL = "https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FMG&QO_fu146_anzr=Nv4%20Pn44vr4"
FIELDS = ["YEAR", "MONTH", "UNIQUE_CARRIER", "ORIGIN", "DEST", "DEST_COUNTRY", "DISTANCE",
          "DEPARTURES_PERFORMED", "SEATS", "PASSENGERS", "FREIGHT", "AIRCRAFT_CONFIG", "CLASS"]


def form_state(html: str) -> dict:
    """All hidden inputs (__VIEWSTATE etc.) from the page."""
    return dict(re.findall(r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]+value="([^"]*)"', html))


def download(client: httpx.Client, year: str, period: str) -> tuple[bytes, float]:
    page = client.get(URL)
    data = form_state(page.text)
    data.update({"cboGeography": "All", "cboYear": year, "cboPeriod": period,
                 "chkDownloadZip": "on", "btnDownload": "Download"})
    for f in FIELDS:
        data[f] = "on"
    with Timer() as t:
        r = client.post(URL, data=data)
    r.raise_for_status()
    return r.content, t.seconds


def main() -> None:
    year = sys.argv[1] if len(sys.argv) > 1 else "2025"
    period = sys.argv[2] if len(sys.argv) > 2 else "1"   # month number, or "All"
    result = {"source": "TranStats T-100 Segment (All Carriers), table FMG", "year": year, "period": period}
    with httpx.Client(timeout=600, follow_redirects=True, headers=UA) as client:
        try:
            content, seconds = download(client, year, period)
        except Exception as e:
            result.update(works=False, error=f"{type(e).__name__}: {e}")
            return save(f"transtats_t100_route_{year}_{period}", result)

    result.update(download_seconds=seconds, response_bytes=len(content))
    if not content.startswith(b"PK"):
        result.update(works=False, note="response is not a zip", head=content[:300].decode("utf-8", "replace"))
        return save(f"transtats_t100_route_{year}_{period}", result)

    zf = zipfile.ZipFile(io.BytesIO(content))
    csv_name = next(n for n in zf.namelist() if n.upper().startswith("T_") and n.lower().endswith(".csv"))
    df = pd.read_csv(zf.open(csv_name), low_memory=False)
    anc = df[df["ORIGIN"] == "ANC"]
    result.update(
        works=True,
        csv_rows=len(df),
        csv_uncompressed_mb=round(zf.getinfo(csv_name).file_size / 1e6, 1),
        columns=list(df.columns),
        aircraft_config_values=df["AIRCRAFT_CONFIG"].value_counts().to_dict(),
        class_values=df["CLASS"].value_counts().to_dict(),
        carriers=df["UNIQUE_CARRIER"].nunique(),
        anc_sample={
            "rows": len(anc),
            "departures_by_aircraft_config": anc.groupby("AIRCRAFT_CONFIG")["DEPARTURES_PERFORMED"].sum().to_dict(),
            "departures_over_4000km": float(anc.loc[anc["DISTANCE"] * 1.609344 > 4000, "DEPARTURES_PERFORMED"].sum()),
            "departures_total": float(anc["DEPARTURES_PERFORMED"].sum()),
        },
    )

    # A-06a: at ANC, which carriers fly freighters (config 2) AND passenger aircraft (config 1)?
    # Those mixed-fleet carriers are the ones a callsign-prefix list would misclassify.
    by = anc.pivot_table(index="UNIQUE_CARRIER", columns="AIRCRAFT_CONFIG", values="DEPARTURES_PERFORMED",
                         aggfunc="sum", fill_value=0)
    by.columns = [f"config_{c}" for c in by.columns]
    mixed = by[(by.get("config_1", 0) > 0) & (by.get("config_2", 0) > 0)]
    result["anc_carriers"] = {
        "freighter_carriers": by[by.get("config_2", 0) > 0].sort_values("config_2", ascending=False)
                               .head(25)["config_2"].astype(int).to_dict(),
        "mixed_fleet_carriers": mixed.astype(int).to_dict(orient="index"),
        "mixed_fleet_freighter_departures": int(mixed.get("config_2", pd.Series(dtype=float)).sum()),
    }

    # A-06a gap: freighter departures at ANC by carriers whose callsign prefix is NOT on the config list.
    # T-100 uses IATA carrier codes; this IATA -> ICAO mapping of the config list is approximate (hand-made).
    cargo_list_iata = {"FX": "FDX", "5X": "UPS", "5Y": "GTI", "PO": "PAC", "K4": "CKS", "GB": "ABX",
                       "8C": "ATN", "KD": "WGN", "CV": "CLX", "KZ": "NCA", "CK": "CKK", "NC": "NAC", "L2": "LYC"}
    fr = anc[anc["AIRCRAFT_CONFIG"] == 2]
    on_list = fr["UNIQUE_CARRIER"].isin(cargo_list_iata)
    result["anc_callsign_gap"] = {
        "freighter_departures": int(fr["DEPARTURES_PERFORMED"].sum()),
        "by_carriers_on_cargo_list": int(fr.loc[on_list, "DEPARTURES_PERFORMED"].sum()),
        "by_carriers_not_on_list": int(fr.loc[~on_list, "DEPARTURES_PERFORMED"].sum()),
        "share_missed_by_callsign_rule": round(float(fr.loc[~on_list, "DEPARTURES_PERFORMED"].sum()
                                                     / fr["DEPARTURES_PERFORMED"].sum()), 3),
    }
    dist_km = anc["DISTANCE"] * 1.609344
    def lh(mask, thr):
        d = anc.loc[mask, "DEPARTURES_PERFORMED"]
        return round(float(d[dist_km[mask] > thr].sum() / d.sum()), 3) if d.sum() else None
    pax_mask, all_mask = anc["AIRCRAFT_CONFIG"] == 1, anc["AIRCRAFT_CONFIG"].notna()
    result["anc_long_haul_share"] = {
        "passenger_aircraft": {"4000km": lh(pax_mask, 4000), "3500km": lh(pax_mask, 3500)},
        "all_aircraft": {"4000km": lh(all_mask, 4000), "3500km": lh(all_mask, 3500)},
        "freighters": {"4000km": lh(anc["AIRCRAFT_CONFIG"] == 2, 4000)},
    }

    # Checklist #6: airport x carrier seats -> ULCC share is computable.
    ulcc = {"NK", "F9", "G4", "SY"}   # Spirit, Frontier, Allegiant, Sun Country (illustrative, A-11 TBD)
    pax = df[df["AIRCRAFT_CONFIG"] == 1]
    seats = pax.groupby("ORIGIN")["SEATS"].sum()
    ulcc_seats = pax[pax["UNIQUE_CARRIER"].isin(ulcc)].groupby("ORIGIN")["SEATS"].sum()
    share = (ulcc_seats / seats).fillna(0)
    result["ulcc_seat_share_sample"] = {a: round(float(share.get(a, 0)), 3)
                                        for a in ["BOS", "PVD", "BDL", "MHT", "PWM", "LAX", "SNA", "SFO", "LAS", "MCO", "FLL"]}
    save(f"transtats_t100_route_{year}_{period}", result)


if __name__ == "__main__":
    main()
