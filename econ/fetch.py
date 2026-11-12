"""Command-line refresh.

    python -m econ.fetch --years 2022 2023 2024 2025   # download + load real BPS data
    python -m econ.fetch --probe                       # print one raw response to check field names
    python -m econ.fetch --demo                        # load SYNTHETIC demo data (for trying the UI only)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

from . import bps_trade, db


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def probe() -> None:
    import requests
    key = bps_trade.api_key()
    year = dt.date.today().year - 1
    url = bps_trade.build_url("export", "27", year, key)
    print("GET", url.replace(key, "<KEY>"))
    payload = requests.get(url, timeout=60).json()
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
    rows, pages = bps_trade._extract_page(payload)
    print(f"\n{len(rows)} rows on page 1 of {pages}")
    if rows:
        print("Fields in first row:", list(rows[0].keys()))
        parsed = bps_trade.parse_records(rows[:5], "export", year)
        print("Parsed sample:", json.dumps(parsed[:3], indent=2, default=str))
        if not parsed:
            print("!! Nothing parsed: the month field name is probably different. "
                  "Update FIELD_CANDIDATES in econ/bps_trade.py.")


def refresh(years: list[int], flows: list[str], force: bool) -> None:
    con = db.connect()
    for flow in flows:
        for year in years:
            rows = []
            for path in bps_trade.download([flow], [year], force=force):
                rows.extend(bps_trade.load_raw_file(path))
            n = db.replace_year(con, flow, year, rows)
            print(f"{flow} {year}: {n:,} rows")
    db.set_meta(con, "source", "BPS")
    db.set_meta(con, "refreshed_at", dt.datetime.now().isoformat(timespec="minutes"))
    con.close()


def main() -> None:
    _load_env()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    this_year = dt.date.today().year
    p.add_argument("--years", type=int, nargs="+", default=[this_year - 1, this_year])
    p.add_argument("--flows", nargs="+", default=["export", "import"], choices=["export", "import"])
    p.add_argument("--force", action="store_true", help="re-download files already in data/raw")
    p.add_argument("--probe", action="store_true")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.probe:
        probe()
    elif a.demo:
        from . import demo
        demo.load_demo()
    else:
        refresh(a.years, a.flows, a.force)


if __name__ == "__main__":
    main()
