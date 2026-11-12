"""Fetch Indonesian trade data from the BPS Web API (`dataexim` endpoint).

One request = one flow (export/import), one HS code, one year. Records come back
aggregated by HS code x Indonesian port x partner country, with USD value and
net weight. We fetch every HS2 chapter for each year and keep the raw JSON in
data/raw/ so the parser can be fixed later without re-downloading.

Field names below were taken from the stadata SDK docs (kodehs, pod, ctr, tahun).
The names for value, net weight and month are not documented, so `FIELD_CANDIDATES`
lists the likely spellings. Run `python -m econ.fetch --probe` once with a real
key to confirm them.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Iterable, Iterator

import requests

BASE_URL = "https://webapi.bps.go.id/v1/api/dataexim"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

FLOW_CODES = {"export": 1, "import": 2}
HS2_CHAPTERS = [f"{i:02d}" for i in range(1, 98) if i != 77]  # chapter 77 is reserved

FIELD_CANDIDATES = {
    "hs": ["kodehs", "hs", "kode_hs"],
    "hs_desc": ["deskripsi", "uraian", "desc", "hs_desc", "keterangan"],
    "port": ["pod", "pelabuhan", "port"],
    "country": ["ctr", "negara", "country"],
    "year": ["tahun", "year"],
    "month": ["bulan", "month"],
    "value_usd": ["value", "nilai", "fob", "cif", "nilai_usd"],
    "netweight_kg": ["netweight", "netwt", "berat", "berat_bersih", "weight", "netto"],
}

MONTHS_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "august": 8, "october": 10, "december": 12,
}


def api_key() -> str:
    key = os.environ.get("BPS_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "BPS_API_KEY is not set. Register for a free key at https://webapi.bps.go.id "
            "and put it in .env (see .env.example)."
        )
    return key


def build_url(flow: str, hs_code: str, year: int, key: str, monthly: bool = True) -> str:
    jenishs = 1 if len(hs_code) == 2 else 2
    return (
        f"{BASE_URL}/sumber/{FLOW_CODES[flow]}/kodehs/{hs_code}/jenishs/{jenishs}"
        f"/tahun/{year}/periode/{1 if monthly else 2}/key/{key}/"
    )


class BPSError(RuntimeError):
    pass


def _get_json(session: requests.Session, url: str, key: str, retries: int = 8) -> dict:
    """GET with backoff. BPS returns 429 when called too fast; wait and retry.
    Error messages never include the API key."""
    safe = url.replace(key, "<KEY>")
    wait = 5.0
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=60)
        except requests.RequestException as e:
            err = f"network error: {type(e).__name__}"
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                ra = resp.headers.get("Retry-After", "")
                delay = float(ra) if ra.isdigit() else wait
                err = f"HTTP {resp.status_code}"
                print(f"  {err}, waiting {delay:.0f}s (attempt {attempt + 1}/{retries})", flush=True)
                time.sleep(delay)
                wait = min(wait * 2, 120)
                continue
            if resp.status_code >= 400:
                raise BPSError(f"HTTP {resp.status_code} for {safe}")
            try:
                return resp.json()
            except ValueError:
                err = "response was not JSON"
        time.sleep(wait)
        wait = min(wait * 2, 120)
    raise BPSError(f"gave up after {retries} attempts ({err}) for {safe}")


def fetch_one(flow: str, hs_code: str, year: int, key: str, session: requests.Session) -> dict:
    """Fetch one flow/HS/year, following pagination. Returns {'records': [...]}."""
    records: list[dict] = []
    page = 1
    while True:
        url = build_url(flow, hs_code, year, key)
        if page > 1:
            url += f"?page={page}"
        payload = _get_json(session, url, key)
        recs, total_pages = _extract_page(payload)
        records.extend(recs)
        if page >= total_pages:
            break
        page += 1
    return {"records": records}


def _extract_page(payload: dict) -> tuple[list[dict], int]:
    """BPS responses usually look like {"status": "OK", "data-availability": ..., "data": [meta, [rows]]}
    or {"data": [rows]}; handle both."""
    data = payload.get("data", [])
    total_pages = 1
    rows: list[dict] = []
    if isinstance(data, list) and data and isinstance(data[0], dict) and "pages" in data[0]:
        total_pages = int(data[0].get("pages") or 1)
        rows = data[1] if len(data) > 1 and isinstance(data[1], list) else []
    elif isinstance(data, list):
        rows = [r for r in data if isinstance(r, dict)]
    return rows, total_pages


def raw_path(flow: str, hs_code: str, year: int) -> Path:
    return RAW_DIR / flow / str(year) / f"{hs_code}.json"


def download(flows: Iterable[str], years: Iterable[int], chapters: Iterable[str] = HS2_CHAPTERS,
             force: bool = False, pause: float = 1.5) -> Iterator[Path]:
    """Download raw files, skipping ones already on disk, so an interrupted run
    can simply be started again and it carries on where it stopped."""
    key = api_key()
    session = requests.Session()
    for flow in flows:
        for year in years:
            chapters = list(chapters)
            for i, hs in enumerate(chapters, 1):
                path = raw_path(flow, hs, year)
                if path.exists() and not force:
                    yield path
                    continue
                print(f"{flow} {year} HS{hs} ({i}/{len(chapters)})", flush=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                result = fetch_one(flow, hs, year, key, session)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(result, ensure_ascii=False))
                tmp.replace(path)
                time.sleep(pause)
                yield path


def _pick(rec: dict, field: str):
    lower = {k.lower(): v for k, v in rec.items()}
    for cand in FIELD_CANDIDATES[field]:
        if cand in lower and lower[cand] not in (None, ""):
            return lower[cand]
    return None


def _to_float(x) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


_BRACKET = re.compile(r"^\s*\[(\w+)\]\s*(.*)$")


def _split_code(x) -> tuple[str, str | None]:
    """BPS returns labels like "[27] Bahan bakar mineral" or "[01] Januari"."""
    s = str(x or "").strip()
    m = _BRACKET.match(s)
    return (m.group(1), m.group(2).strip() or None) if m else (s, None)


def _to_month(x) -> int | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return int(x)
    s = _split_code(x)[0].lower()
    if s.isdigit():
        return int(s)
    return MONTHS_ID.get(s)


def parse_records(records: list[dict], flow: str, default_year: int) -> list[dict]:
    """Normalise raw API rows into our trade schema. Rows without a month are skipped
    (they would be annual totals)."""
    out = []
    for rec in records:
        month = _to_month(_pick(rec, "month"))
        if month is None or not 1 <= month <= 12:
            continue
        hs, hs_label = _split_code(_pick(rec, "hs"))
        out.append({
            "flow": flow,
            "year": int(_pick(rec, "year") or default_year),
            "month": month,
            "hs_code": hs,
            "hs2": hs[:2].zfill(2) if hs else None,
            "hs_desc": _pick(rec, "hs_desc") or hs_label,
            "port": (str(_pick(rec, "port") or "").strip().upper() or "UNKNOWN"),
            "country": (str(_pick(rec, "country") or "").strip().upper() or "UNKNOWN"),
            "value_usd": _to_float(_pick(rec, "value_usd")) or 0.0,
            "netweight_kg": _to_float(_pick(rec, "netweight_kg")),
        })
    return out


def load_raw_file(path: Path) -> list[dict]:
    flow = path.parent.parent.name
    year = int(path.parent.name)
    payload = json.loads(path.read_text())
    return parse_records(payload.get("records", []), flow, year)
