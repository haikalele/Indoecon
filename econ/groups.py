"""Reference mappings: HS2 chapter -> readable product group, HS2 -> approximate import
use category, Indonesian port -> province, partner country -> region group.

These are deliberately simple and editable. The import-use split here is an HS2
approximation of BPS's "golongan penggunaan barang" (which BPS builds from detailed
codes); chapters 84/85/87 mix capital goods, parts and consumer items.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

REF_DIR = Path(__file__).resolve().parent.parent / "ref"

# (first chapter, last chapter, group name)
PRODUCT_GROUPS: list[tuple[int, int, str]] = [
    (1, 5, "Animal & fish products"),
    (6, 14, "Crops, coffee & spices"),
    (15, 15, "Palm oil & veg oils"),
    (16, 24, "Processed food & tobacco"),
    (25, 26, "Ores & minerals"),
    (27, 27, "Coal, oil & gas"),
    (28, 38, "Chemicals"),
    (39, 40, "Plastics & rubber"),
    (41, 43, "Leather goods"),
    (44, 49, "Wood, pulp & paper"),
    (50, 60, "Textiles & yarn"),
    (61, 63, "Garments"),
    (64, 67, "Footwear"),
    (68, 70, "Stone, ceramics & glass"),
    (71, 71, "Gold & jewellery"),
    (72, 73, "Iron, steel & ferronickel"),
    (74, 74, "Copper"),
    (75, 75, "Nickel"),
    (76, 76, "Aluminium"),
    (78, 83, "Other metals & metal goods"),
    (84, 84, "Machinery"),
    (85, 85, "Electrical & electronics"),
    (86, 89, "Vehicles & transport"),
    (90, 92, "Instruments"),
    (94, 94, "Furniture"),
    (93, 99, "Other manufactures"),
]

CONSUMER = {2, 3, 4, 7, 8, 9, 16, 17, 18, 19, 20, 21, 22, 24, 30, 33, 42, 61, 62, 63,
            64, 65, 71, 91, 92, 94, 95, 96}
CAPITAL = {84, 85, 86, 88, 89, 90}


def product_group(hs2: str | int | None) -> str:
    try:
        ch = int(hs2)
    except (TypeError, ValueError):
        return "Unclassified"
    for lo, hi, name in PRODUCT_GROUPS:
        if lo <= ch <= hi:
            return name
    return "Unclassified"


def import_use(hs2: str | int | None) -> str:
    try:
        ch = int(hs2)
    except (TypeError, ValueError):
        return "Unclassified"
    if ch == 27:
        return "Fuels"
    if ch in CONSUMER:
        return "Consumer goods"
    if ch in CAPITAL:
        return "Capital goods"
    return "Raw materials & intermediates"


@lru_cache
def _port_rules() -> list[tuple[str, str]]:
    with open(REF_DIR / "ports_province.csv", newline="") as f:
        rows = [(r["keyword"].strip().upper(), r["province"].strip()) for r in csv.DictReader(f)]
    # longest keyword first so "SOEKARNO HATTA MAKASSAR" beats "SOEKARNO HATTA"
    return sorted(rows, key=lambda r: -len(r[0]))


def port_province(port: str | None) -> str:
    p = (port or "").upper()
    for kw, prov in _port_rules():
        if kw in p:
            return prov
    return "Unmapped"


@lru_cache
def _country_regions() -> dict[str, str]:
    with open(REF_DIR / "country_regions.csv", newline="") as f:
        return {r["country"].strip().upper(): r["region"].strip() for r in csv.DictReader(f)}


def country_region(country: str | None) -> str:
    return _country_regions().get((country or "").upper(), "Rest of world")
