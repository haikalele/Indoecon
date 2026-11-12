import pandas as pd

from econ import bps_trade, db, groups


def test_parse_records_handles_names_and_formats():
    rows = [
        {"kodehs": "27011900", "pod": "Tarahan ", "ctr": "China", "tahun": "2024",
         "bulan": "Maret", "value": "1,234.5", "netweight": 1000},
        {"kodehs": "27", "pod": "X", "ctr": "Y", "tahun": 2024, "value": 5},  # annual row, no month
    ]
    out = bps_trade.parse_records(rows, "export", 2024)
    assert len(out) == 1
    r = out[0]
    assert (r["month"], r["hs2"], r["port"], r["country"]) == (3, "27", "TARAHAN", "CHINA")
    assert r["value_usd"] == 1234.5 and r["netweight_kg"] == 1000.0


def test_extract_page_paginated_and_flat():
    rows, pages = bps_trade._extract_page({"data": [{"page": 1, "pages": 3}, [{"a": 1}]]})
    assert rows == [{"a": 1}] and pages == 3
    rows, pages = bps_trade._extract_page({"data": [{"a": 1}]})
    assert rows == [{"a": 1}] and pages == 1


def test_build_url():
    u = bps_trade.build_url("import", "8471", 2024, "K")
    assert u.endswith("/sumber/2/kodehs/8471/jenishs/2/tahun/2024/periode/1/key/K/")


def test_groups():
    assert groups.product_group("15") == "Palm oil & veg oils"
    assert groups.product_group("94") == "Furniture"
    assert groups.product_group("95") == "Other manufactures"
    assert groups.import_use("84") == "Capital goods"
    assert groups.import_use("27") == "Fuels"
    assert groups.port_province("SOEKARNO HATTA MAKASSAR") == "Sulawesi Selatan"
    assert groups.port_province("SOEKARNO HATTA") == "Banten"
    assert groups.port_province("NOWHERE") == "Unmapped"
    assert groups.country_region("Tiongkok") == "China"


def _df():
    p = pd.date_range("2023-01-01", "2024-12-01", freq="MS")
    a = pd.DataFrame({"period": p, "port": "A", "value_usd": 100.0})
    b = pd.DataFrame({"period": p, "port": "B", "value_usd": [10e6] * 12 + [30e6] * 12})
    return pd.concat([a, b])


def test_monthly_series_yoy():
    s = db.monthly_series(_df(), by="port")
    b = s[(s.port == "B") & (s.period == "2024-03-01")].iloc[0]
    assert round(b.yoy_pct) == 200 and round(b.roll3_yoy_pct) == 200


def test_movers_hides_tiny_and_ranks():
    m = db.movers(_df(), "port", pd.Timestamp("2024-06-01"))
    assert m.port.tolist() == ["B"] and m.change_usd.iloc[0] == 20e6


def test_replace_year_idempotent(tmp_path):
    con = db.connect(tmp_path / "t.duckdb")
    row = dict(flow="export", year=2024, month=1, hs_code="27", hs2="27", hs_desc=None,
               port="P", country="C", value_usd=1.0, netweight_kg=None)
    db.replace_year(con, "export", 2024, [row])
    db.replace_year(con, "export", 2024, [row, {**row, "month": 2}])
    assert con.execute("select count(*) from trade").fetchone()[0] == 2
