"""Phase 0 checklist #2: can code fetch TranStats airline delay causes (carrier x airport x month)?

OT_DelayCause1.asp is a plain form (PeriodFrom / PeriodTo, coded as year*12 + month). Posting it
returns a page whose "Download Raw Data" link is a plain GET for a zip (Airline_Delay_Cause.csv)
covering that range. We measure size/latency and compute a sample NAS delay share
(nas_delay minutes / total arrival delay minutes) over the latest 12 months.
"""

import io
import re
import zipfile

import httpx
import pandas as pd

from _common import UA, Timer, save

BASE = "https://www.transtats.bts.gov/OT_Delay/"
AIRPORTS = ["SFO", "LGA", "EWR", "DCA", "SNA", "LAX", "BOS", "PVD", "ANC"]


def download_link(client: httpx.Client) -> tuple[str, int, int]:
    """Post the form for the latest 12 available months and return the raw-data link."""
    page = client.get(BASE + "OT_DelayCause1.asp?20=E").text
    latest = int(re.search(r"name='PeriodTo'.*?value\s*=\s*'?(\d+)", page, re.S | re.I).group(1))
    page = client.post(BASE + "OT_DelayCause1.asp?20=E",
                       data={"Carrier": "All", "Airport": "All", "PeriodFrom": str(latest - 11),
                             "PeriodTo": str(latest)}).text
    href = re.search(r"href='(ot_delaycause1_DL\.aspx[^']+)'", page, re.I).group(1)
    return BASE + href, latest - 11, latest


def main() -> None:
    result = {"source": "TranStats Airline On-Time: delay causes (Airline_Delay_Cause.csv)"}
    with httpx.Client(timeout=300, follow_redirects=True, headers=UA) as client:
        url, p_from, p_to = download_link(client)
        result["requested_periods"] = [p_from, p_to]
        with Timer() as t:
            r = client.get(url)
    result.update(download_seconds=t.seconds, response_bytes=len(r.content),
                  content_type=r.headers.get("content-type"))
    if not r.content.startswith(b"PK"):
        result.update(works=False, head=r.content[:300].decode("utf-8", "replace"))
        return save("transtats_delay_causes", result)

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    name = zf.namelist()[0]
    df = pd.read_csv(zf.open(name))
    df.columns = [c.strip() for c in df.columns]
    df["ym"] = df["year"].astype(int) * 100 + df["month"].astype(int)
    result.update(
        works=True,
        file=name,
        rows=len(df),
        columns=list(df.columns),
        first_month=int(df["ym"].min()),
        latest_month=int(df["ym"].max()),
        months=int(df["ym"].nunique()),
        airports=int(df["airport"].nunique()),
    )

    # NAS delay share over the latest 12 months in the file.
    months = sorted(df["ym"].unique())[-12:]
    last12 = df[df["ym"].isin(months)]
    g = last12.groupby("airport")[["arr_delay", "nas_delay", "arr_flights"]].sum()
    g["nas_share_of_delay_minutes"] = (g["nas_delay"] / g["arr_delay"]).round(3)
    result["nas_share_sample_latest12"] = g.loc[g.index.intersection(AIRPORTS), "nas_share_of_delay_minutes"].to_dict()
    result["nas_share_window"] = f"{months[0]} .. {months[-1]}"
    save("transtats_delay_causes", result)


if __name__ == "__main__":
    main()
