# indoecon: Indonesia trade signals

A personal dashboard for reading Indonesian export and import data as market signals.
It's the first module of a larger Indonesian economic dashboard (BKPM investment, macro panel
and cross-link views come later).

## What it answers

1. **What's moving this month?** The *Biggest movers* tab ranks product groups, Indonesian ports
   and partner countries by USD change against the same month a year earlier.
2. **Which ports and regions are heating up or cooling down?** The *Ports & regions* tab shows
   each province or port with its YoY change and 3-month rolling trend, and what passes through it.
3. **What do imports say about domestic demand?** The *Import demand* tab splits imports into raw
   materials, capital goods, consumer goods and fuels.

Every view has the same filters: flow (export or import), reference month and chart window.

## Data

Source: the BPS Web API `dataexim` endpoint. Each record is HS code × Indonesian port × partner
country × month, with USD value and net weight. We pull every HS2 chapter for each year
(about 96 requests per flow per year) and keep the raw JSON in `data/raw/`, so re-parsing never
needs a re-download.

* Exports are by **port of loading** and **destination country**. Imports are by
  **port of unloading** and **origin country**.
* Product groups (`econ/groups.py`) put HS2 chapters into about 25 readable groups, such as
  "Palm oil & veg oils" and "Iron, steel & ferronickel".
* The import end-use split is **approximate**. It's mapped from HS chapters, while BPS uses detailed
  codes. Replacing it with BPS's own end-use (BEC) table is on the roadmap.
* Ports are mapped to provinces with keyword rules in `ref/ports_province.csv`. Ports that don't
  match show as "Unmapped". Add them as they appear.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then paste your BPS key
python -m econ.fetch --probe              # check one live response and the field names
python -m econ.fetch --years 2022 2023 2024 2025 2026
streamlit run app.py
```

To get a key, register at https://webapi.bps.go.id and create an app. The key is free.

To try the screens without a key, run `python -m econ.fetch --demo`. This loads **synthetic**
numbers, and the app shows a warning banner while they're loaded. A real fetch replaces them.

### Monthly refresh

BPS releases trade data around the 15th of each month, for the month before last. To refresh,
re-run the current year:

```bash
python -m econ.fetch --years 2026 --force
```

Schedule it monthly with cron or Windows Task Scheduler. Each flow and year is replaced as a
whole, so re-running is safe.

## Known gaps, to verify with a live key

* The BPS response field names for **value, net weight and month** aren't documented. The parser
  tries the likely names (`FIELD_CANDIDATES` in `econ/bps_trade.py`). `--probe` prints the real
  ones. If nothing parses, add the right names there.
* We don't know yet how far back port-level monthly data goes.

## Roadmap

1. Run the live data check and fix the field names. Backfill 2015 onward.
2. Add a volume view (net weight and implied unit price) for coal, CPO, nickel and steel, to separate price moves from volume moves.
3. Replace the approximate import end use with BPS's own end-use classification.
4. Add a province of origin view, which BPS publishes separately from the port.
5. Add the BKPM PMA/PMDN module, then the macro panel, then cross-link views.

## Layout

```
app.py              Streamlit dashboard
econ/bps_trade.py   BPS API client and parser
econ/db.py          DuckDB storage and analytics (YoY, rolling, movers)
econ/groups.py      product groups, import end use, port→province, country→region
econ/fetch.py       CLI: --years / --probe / --demo
econ/demo.py        synthetic demo data
ref/*.csv           editable mapping tables
tests/              pytest
```
