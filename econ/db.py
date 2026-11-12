"""DuckDB storage and the analytics queries the dashboard uses."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from . import groups

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trade.duckdb"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trade (
    flow          VARCHAR,   -- 'export' | 'import'
    year          INTEGER,
    month         INTEGER,
    period        DATE,      -- first day of month
    hs_code       VARCHAR,
    hs2           VARCHAR,
    hs_desc       VARCHAR,
    port          VARCHAR,   -- Indonesian port of loading (exports) / unloading (imports)
    country       VARCHAR,   -- destination (exports) / origin (imports)
    value_usd     DOUBLE,
    netweight_kg  DOUBLE
);
CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR);
"""


def connect(path: Path | str = DB_PATH, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only)
    if not read_only:
        con.execute(SCHEMA)
    return con


def replace_year(con, flow: str, year: int, rows: list[dict]) -> int:
    """Replace one flow/year slice atomically so re-running a refresh is safe."""
    df = pd.DataFrame(rows)
    con.execute("BEGIN")
    con.execute("DELETE FROM trade WHERE flow = ? AND year = ?", [flow, year])
    if not df.empty:
        df["period"] = pd.to_datetime(dict(year=df.year, month=df.month, day=1)).dt.date
        cols = ["flow", "year", "month", "period", "hs_code", "hs2", "hs_desc", "port",
                "country", "value_usd", "netweight_kg"]
        con.register("incoming", df[cols])
        con.execute("INSERT INTO trade SELECT * FROM incoming")
        con.unregister("incoming")
    con.execute("COMMIT")
    return len(df)


def set_meta(con, key: str, value: str) -> None:
    con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", [key, value])


def get_meta(con, key: str) -> str | None:
    row = con.execute("SELECT value FROM meta WHERE key = ?", [key]).fetchone()
    return row[0] if row else None


def load_enriched(con) -> pd.DataFrame:
    """Monthly rows aggregated to HS2 x port x country, with readable groups attached."""
    df = con.execute("""
        SELECT flow, period, hs2, port, country,
               SUM(value_usd) AS value_usd, SUM(netweight_kg) AS netweight_kg
        FROM trade GROUP BY ALL
    """).df()
    if df.empty:
        return df
    df["period"] = pd.to_datetime(df["period"])
    df["product_group"] = df["hs2"].map(groups.product_group)
    df["import_use"] = df["hs2"].map(groups.import_use)
    df["province"] = df["port"].map(groups.port_province)
    df["region"] = df["country"].map(groups.country_region)
    return df


# ---------- analytics helpers (pure pandas, used by the app and tests) ----------

def monthly_series(df: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    """Monthly totals with YoY % and 3-month rolling sum, optionally per category."""
    keys = ["period"] + ([by] if by else [])
    s = df.groupby(keys, as_index=False)["value_usd"].sum().sort_values(keys)
    if by:
        # fill missing months with 0 so shifts line up
        full = pd.MultiIndex.from_product(
            [pd.date_range(s.period.min(), s.period.max(), freq="MS"), s[by].unique()],
            names=["period", by])
        s = s.set_index(["period", by]).reindex(full, fill_value=0).reset_index()
        g = s.groupby(by)["value_usd"]
        s["roll3"] = g.transform(lambda x: x.rolling(3, min_periods=3).sum())
        s["yoy_pct"] = g.transform(lambda x: x.pct_change(12, fill_method=None) * 100)
        s["roll3_yoy_pct"] = s.groupby(by)["roll3"].transform(
            lambda x: x.pct_change(12, fill_method=None) * 100)
    else:
        s = s.set_index("period").asfreq("MS", fill_value=0).reset_index()
        s["roll3"] = s["value_usd"].rolling(3, min_periods=3).sum()
        s["yoy_pct"] = s["value_usd"].pct_change(12, fill_method=None) * 100
        s["roll3_yoy_pct"] = s["roll3"].pct_change(12, fill_method=None) * 100
    return s.replace([float("inf"), float("-inf")], pd.NA)


def movers(df: pd.DataFrame, by: str, month: pd.Timestamp, min_base_usd: float = 5e6,
           top: int = 10) -> pd.DataFrame:
    """Biggest movers for `month` vs the same month a year earlier, by USD change.
    `min_base_usd` hides tiny categories whose % change is meaningless."""
    prev = month - pd.DateOffset(years=1)
    cur = df[df.period == month].groupby(by)["value_usd"].sum()
    old = df[df.period == prev].groupby(by)["value_usd"].sum()
    m = pd.concat([cur.rename("this_month"), old.rename("year_ago")], axis=1).fillna(0)
    m["change_usd"] = m["this_month"] - m["year_ago"]
    m["change_pct"] = (m["change_usd"] / m["year_ago"].where(m["year_ago"] >= min_base_usd)) * 100
    m = m[(m["this_month"] >= min_base_usd) | (m["year_ago"] >= min_base_usd)]
    m = m.reindex(m["change_usd"].abs().sort_values(ascending=False).index)
    return m.head(top).reset_index()
