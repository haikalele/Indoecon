"""SYNTHETIC data so the dashboard can be tried before a BPS key is set up.
Numbers are made up; the app shows a warning banner whenever this data is loaded."""
from __future__ import annotations

import datetime as dt

import numpy as np

from . import db

EXPORT_LINES = [  # (hs2, port, country, base USD per month)
    ("27", "TARAHAN", "CHINA", 900e6), ("27", "SAMARINDA", "INDIA", 700e6),
    ("27", "BANJARMASIN", "CHINA", 600e6), ("15", "DUMAI", "INDIA", 500e6),
    ("15", "BELAWAN", "CHINA", 300e6), ("72", "MOROWALI", "CHINA", 1200e6),
    ("72", "WEDA", "CHINA", 500e6), ("75", "WEDA", "CHINA", 250e6),
    ("74", "AMAMAPARE", "JAPAN", 300e6), ("85", "BATAM", "SINGAPORE", 350e6),
    ("85", "BATAM", "UNITED STATES", 200e6), ("61", "TANJUNG PRIOK", "UNITED STATES", 250e6),
    ("64", "TANJUNG EMAS", "UNITED STATES", 180e6), ("87", "TANJUNG PRIOK", "PHILIPPINES", 220e6),
    ("44", "TANJUNG PERAK", "JAPAN", 120e6), ("94", "TANJUNG EMAS", "UNITED STATES", 90e6),
]
IMPORT_LINES = [
    ("84", "TANJUNG PRIOK", "CHINA", 900e6), ("85", "TANJUNG PRIOK", "CHINA", 800e6),
    ("27", "DUMAI", "SINGAPORE", 1100e6), ("27", "MERAK", "MALAYSIA", 400e6),
    ("10", "TANJUNG PERAK", "AUSTRALIA", 250e6), ("72", "TANJUNG PRIOK", "JAPAN", 300e6),
    ("39", "TANJUNG PERAK", "SOUTH KOREA", 250e6), ("87", "TANJUNG PRIOK", "THAILAND", 200e6),
    ("30", "SOEKARNO HATTA", "INDIA", 80e6), ("84", "MOROWALI", "CHINA", 300e6),
]


def _rows(flow, lines, start, months, rng):
    rows = []
    for i, (hs2, port, ctr, base) in enumerate(lines):
        trend = rng.normal(0.004, 0.006)
        for m in range(months):
            d = (start.year * 12 + start.month - 1 + m)
            y, mo = divmod(d, 12)
            season = 1 + 0.06 * np.sin((mo + i) / 12 * 2 * np.pi)
            val = base * (1 + trend) ** m * season * rng.lognormal(0, 0.08)
            rows.append(dict(flow=flow, year=y, month=mo + 1, hs_code=hs2, hs2=hs2, hs_desc=None,
                             port=port, country=ctr, value_usd=float(val),
                             netweight_kg=float(val / rng.uniform(0.3, 3))))
    return rows


def load_demo() -> None:
    rng = np.random.default_rng(7)
    today = dt.date.today()
    start = dt.date(today.year - 3, 1, 1)
    months = (today.year - start.year) * 12 + today.month - 2  # through ~2 months ago
    con = db.connect()
    con.execute("DELETE FROM trade")
    for flow, lines in (("export", EXPORT_LINES), ("import", IMPORT_LINES)):
        rows = _rows(flow, lines, start, months, rng)
        for year in sorted({r["year"] for r in rows}):
            db.replace_year(con, flow, year, [r for r in rows if r["year"] == year])
    db.set_meta(con, "source", "DEMO")
    db.set_meta(con, "refreshed_at", dt.datetime.now().isoformat(timespec="minutes"))
    con.close()
    print("Loaded SYNTHETIC demo data into", db.DB_PATH)
