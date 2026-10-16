"""Phase 0 checklist #5: FAA NAS Status (nasstatus.faa.gov), no key.

Two endpoints:
- /api/airport-events (JSON): one object per airport WITH an active event (GDP, ground stop, ...).
- /api/airport-status-information (XML): the classic delay feed.
"Not listed" means "no active event", not an error. We list the fields returned, check SFO, and look
for arrival rate / runway configuration fields.
"""

import json
import xml.etree.ElementTree as ET

import httpx

from _common import UA, Timer, save

BASE = "https://nasstatus.faa.gov/api"
CHECK = ["SFO", "LAX", "SNA", "BOS", "ANC"]


def keys_deep(obj, prefix="") -> set:
    """All dotted key paths in a JSON object (lists collapsed to [])."""
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out |= {f"{prefix}{k}"} | keys_deep(v, f"{prefix}{k}.")
    elif isinstance(obj, list) and obj:
        out |= keys_deep(obj[0], prefix.rstrip(".") + "[].")
    return out


def main() -> None:
    result = {"source": "FAA NAS Status"}
    with httpx.Client(timeout=60, headers=UA) as client:
        with Timer() as t:
            r = client.get(f"{BASE}/airport-events")
        events = r.json()
        result["airport_events"] = {
            "status": r.status_code, "seconds": t.seconds, "bytes": len(r.content),
            "airports_listed": [e["airportId"] for e in events],
            "top_level_keys": sorted(events[0].keys()) if events else [],
            "all_key_paths": sorted(keys_deep(events)),
        }
        result["check_airports"] = {
            a: next(({k: v for k, v in e.items() if v not in (None, [], {})}
                     for e in events if e["airportId"] == a), "not listed (no active event)")
            for a in CHECK
        }
        result["arrival_rate_or_config_fields"] = sorted(
            p for p in keys_deep(events)
            if any(w in p.lower() for w in ("rate", "aar", "config", "runway", "arrival"))
        )

        with Timer() as t:
            r = client.get(f"{BASE}/airport-status-information")
        root = ET.fromstring(r.content)
        result["airport_status_information"] = {
            "status": r.status_code, "seconds": t.seconds, "bytes": len(r.content),
            "update_time": root.findtext("Update_Time"),
            "delay_types": [d.findtext("Name") for d in root.findall("Delay_type")],
            "airports": sorted({a.text for a in root.iter("ARPT")}),
        }
    result["works"] = True
    save("faa_nas", result)


if __name__ == "__main__":
    main()
