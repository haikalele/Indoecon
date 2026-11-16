"""Indonesia trade dashboard (Streamlit).  Run:  python -m streamlit run app.py"""
from __future__ import annotations

import altair as alt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from econ import charts, db

st.set_page_config(page_title="Indonesia trade signals", layout="wide")

# Categorical palette (fixed order, validated); see README "Chart colours".
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#9a9890"
FLOW_NAME = {"export": "Exports", "import": "Imports"}
FLOW_COLOR = {"Exports": SERIES[0], "Imports": SERIES[1]}
BLUES = ["#dbe9fa", "#9cc3f0", "#5e9be3", "#2a78d6", "#1a559e"]
GRID = "rgba(128,128,128,0.18)"


# ---------- formatting ----------

def fmt_usd(x) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    sign, a = ("-" if x < 0 else ""), abs(x)
    if a >= 1e9:
        return f"{sign}${a/1e9:,.2f}B"
    if a >= 1e6:
        return f"{sign}${a/1e6:,.0f}M"
    if a >= 1e3:
        return f"{sign}${a/1e3:,.0f}K"
    return f"{sign}${a:,.0f}"


def fmt_pct(x) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    return "0.0%" if round(x, 1) == 0 else f"{x:+.1f}%"


def fmt_pts(x) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:+.1f} pts"


def style(fig: go.Figure, height: int = 360, unified: bool = True) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=78, b=8),
                      hovermode="x unified" if unified else "closest",
                      title=dict(y=0.98, yanchor="top", x=0, xanchor="left"),
                      legend=dict(orientation="h", y=1.0, yanchor="bottom", x=0, title=None),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False, title=None, hoverformat="%b %Y")
    fig.update_yaxes(gridcolor=GRID, zeroline=False, title=None)
    return fig


def treemap(data: pd.DataFrame, path: list[str], title: str, height: int = 420) -> go.Figure:
    fig = px.treemap(data, path=path, values="value_usd", color="value_usd",
                     color_continuous_scale=BLUES, title=title)
    fig.update_coloraxes(showscale=False)
    labels = [fmt_usd(v) for v in fig.data[0].values]
    fig.update_traces(customdata=[[l] for l in labels],
                      texttemplate="%{label}<br>%{percentRoot:.1%}",
                      hovertemplate="<b>%{label}</b><br>%{customdata[0]}<br>"
                                    "%{percentRoot:.1%} of total<extra></extra>")
    return style(fig, height, unified=False)


@st.cache_data(ttl=600)
def load() -> tuple[pd.DataFrame, dict]:
    if not db.DB_PATH.exists():
        return pd.DataFrame(), {}
    con = db.connect(read_only=True)
    df = db.load_enriched(con)
    meta = {k: db.get_meta(con, k) for k in ("source", "refreshed_at")}
    con.close()
    return df, meta


df, meta = load()
st.title("Indonesia trade signals")

if df.empty:
    st.info("No data yet. Run `python -m econ.fetch --years 2024 2025 2026` "
            "(needs BPS_API_KEY), or `python -m econ.fetch --demo` to try the screens.")
    st.stop()

if meta.get("source") == "DEMO":
    st.warning("**Demo data.** These numbers are synthetic, for trying the screens only. "
               "Load real BPS data with `python -m econ.fetch`.", icon="⚠️")
st.caption(f"Source: {meta.get('source')} · refreshed {meta.get('refreshed_at')} · "
           "values in USD, FOB for exports and CIF for imports")

# ---------- global filters (one row) ----------
c1, c2, c3 = st.columns([1, 1, 2])
flow = c1.radio("Flow", ["export", "import"], horizontal=True, format_func=FLOW_NAME.get)
month = c2.selectbox("Month", sorted(df.period.unique(), reverse=True),
                     format_func=lambda d: pd.Timestamp(d).strftime("%b %Y"))
month = pd.Timestamp(month)
yrs = c3.slider("Chart window (years)", 1, 10, 3)
start = month - pd.DateOffset(years=yrs)

f = df[df.flow == flow]
fw = f[(f.period > start) & (f.period <= month)]
flow_name = FLOW_NAME[flow]
partner_word = "destination" if flow == "export" else "origin"
port_word = "port of loading" if flow == "export" else "port of unloading"
last12_start = month - pd.DateOffset(months=11)
prev12_start, prev12_end = month - pd.DateOffset(months=23), month - pd.DateOffset(months=12)
last12_label = f"{last12_start:%b %Y} – {month:%b %Y}"
prev12_label = f"{prev12_start:%b %Y} – {prev12_end:%b %Y}"

tab_over, tab_move, tab_port, tab_partner, tab_demand = st.tabs(
    ["Overview", "Biggest movers", "Ports & regions", "Partners", "Import demand"])

# ---------- Overview ----------
with tab_over:
    tot = db.monthly_series(df[df.period <= month], by="flow")
    tot["flow"] = tot["flow"].map(FLOW_NAME)
    cur = tot[tot.period == month].set_index("flow")
    exp_v = cur["value_usd"].get("Exports", 0)
    imp_v = cur["value_usd"].get("Imports", 0)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Exports", fmt_usd(exp_v), fmt_pct(cur["yoy_pct"].get("Exports")) + " YoY")
    k2.metric("Imports", fmt_usd(imp_v), fmt_pct(cur["yoy_pct"].get("Imports")) + " YoY")
    k3.metric("Trade balance", fmt_usd(exp_v - imp_v))
    ytd = df[(df.period.dt.year == month.year) & (df.period <= month)]
    ytd_bal = ytd[ytd.flow == "export"].value_usd.sum() - ytd[ytd.flow == "import"].value_usd.sum()
    k4.metric(f"Balance YTD {month.year}", fmt_usd(ytd_bal))

    t = tot[tot.period > start]
    st.altair_chart(charts.line_focus(t, "value_usd", "flow", "Monthly value",
                                      order=["Exports", "Imports"], colors=FLOW_COLOR),
                    use_container_width=True)
    st.altair_chart(charts.line_focus(t, "roll3_yoy_pct", "flow",
                                      "Momentum: last 3 months vs same 3 months a year earlier",
                                      order=["Exports", "Imports"], colors=FLOW_COLOR,
                                      value_title="3-month change"), use_container_width=True)

    comp = f[(f.period >= last12_start) & (f.period <= month)]
    comp = comp.groupby("product_group", as_index=False)["value_usd"].sum()
    st.plotly_chart(treemap(comp, ["product_group"], f"{flow_name} by product group, {last12_label}"),
                    use_container_width=True)

    heat = db.monthly_series(fw, by="product_group")
    heat = heat[heat.period > start]
    by_size = (f[(f.period >= last12_start) & (f.period <= month)]
               .groupby("product_group")["value_usd"].sum().sort_values(ascending=False))
    heat_order = [g for g in by_size.index if by_size[g] > 0]
    st.altair_chart(charts.momentum_heatmap(heat[heat.product_group.isin(heat_order)],
                                            f"{flow_name} momentum by product group", order=heat_order),
                    use_container_width=True)
    st.caption("Each cell compares the latest 3 months with the same 3 months a year earlier, "
               "which cancels out seasonal swings and smooths lumpy shipments. Blue = growing, "
               "orange = shrinking, grey = about flat. Biggest product groups at the top.")

# ---------- Movers ----------
with tab_move:
    st.caption(f"{month:%B %Y} vs {month - pd.DateOffset(years=1):%B %Y}, ranked by change in USD. "
               "Anything under $5M in both months is hidden.")
    cols = st.columns(3)
    for col, (by, label) in zip(cols, [("product_group", "Product group"),
                                        ("port", port_word.capitalize()),
                                        ("country", f"Partner ({partner_word})")]):
        m = db.movers(f, by, month)
        col.subheader(label)
        if m.empty:
            col.write("No comparison available for this month.")
            continue
        mm = m.assign(now_l=m.this_month.map(fmt_usd), ago_l=m.year_ago.map(fmt_usd),
                      chg_l=m.change_usd.map(fmt_usd), pct_l=m.change_pct.map(fmt_pct))
        col.altair_chart(charts.diverging_bars(mm, by, tooltip=[
            alt.Tooltip(f"{by}:N", title=label), alt.Tooltip("chg_l:N", title="Change"),
            alt.Tooltip("pct_l:N", title="Change %"),
            alt.Tooltip("now_l:N", title=f"{month:%b %Y}"),
            alt.Tooltip("ago_l:N", title=f"{month - pd.DateOffset(years=1):%b %Y}")]),
            use_container_width=True)
        col.dataframe(pd.DataFrame({
            label: m[by],
            f"{month:%b %Y}": m.this_month.map(fmt_usd),
            f"{month - pd.DateOffset(years=1):%b %Y}": m.year_ago.map(fmt_usd),
            "Change": m.change_usd.map(fmt_usd),
            "Change %": m.change_pct.map(fmt_pct),
        }), hide_index=True, use_container_width=True)

# ---------- Ports & regions ----------
with tab_port:
    level = st.radio("Group by", ["province", "port"], horizontal=True, format_func=str.title)
    level_name = level.title()
    s = db.monthly_series(fw, by=level)
    last12 = f[(f.period >= last12_start) & (f.period <= month)].groupby(level)["value_usd"].sum()
    top = last12.sort_values(ascending=False).head(8).index.tolist()
    snap = s[s.period == month].set_index(level)
    table = pd.DataFrame({
        f"Last 12 months ({last12_label})": last12.map(fmt_usd),
        f"{month:%b %Y}": snap["value_usd"].map(fmt_usd),
        "Change vs a year ago": snap["yoy_pct"].map(fmt_pct),
        "3-month trend vs a year ago": snap["roll3_yoy_pct"].map(fmt_pct),
        "_sort": last12,
    }).sort_values("_sort", ascending=False).drop(columns="_sort")
    table.index.name = level_name
    st.dataframe(table, use_container_width=True)
    if level == "province" and (fw.province == "Unmapped").any():
        st.caption("'Unmapped' = ports not yet linked to a province in ref/ports_province.csv.")
    pick = st.multiselect(f"Compare {level}s", sorted(s[level].unique()),
                          default=top[:4], max_selections=8)
    if pick:
        order = [p for p in top if p in pick] + [p for p in pick if p not in top]
        st.altair_chart(charts.line_focus(s[s[level].isin(pick)], "roll3", level,
                                          "Value over the last 3 months (rolling total)", order=order,
                                          value_title="3-month value"), use_container_width=True)
    port_sel = st.selectbox(f"What moves through a {level}?", top or sorted(s[level].unique()))
    sub = f[(f[level] == port_sel) & (f.period >= last12_start) & (f.period <= month)]
    mix = sub.groupby(["product_group", "country"], as_index=False)["value_usd"].sum()
    if not mix.empty:
        st.plotly_chart(treemap(mix, ["product_group", "country"],
                                f"{port_sel}: product group, then {partner_word} country, {last12_label}"),
                        use_container_width=True)

# ---------- Partners ----------
with tab_partner:
    now = f[(f.period >= last12_start) & (f.period <= month)].groupby("country")["value_usd"].sum()
    before = f[(f.period >= prev12_start) & (f.period <= prev12_end)].groupby("country")["value_usd"].sum()
    p = pd.DataFrame({"now": now, "before": before}).fillna(0)
    p["growth"] = (p["now"] / p["before"].where(p["before"] > 0) - 1) * 100
    p["share_now"] = p["now"] / p["now"].sum() * 100
    p["share_before"] = p["before"] / max(p["before"].sum(), 1) * 100
    p["share_shift"] = p["share_now"] - p["share_before"]
    p = p.sort_values("now", ascending=False)

    st.markdown(f"**{flow_name} by {partner_word} country.** Comparing the latest 12 months "
                f"(**{last12_label}**) with the 12 months before (**{prev12_label}**).")

    top15 = p.head(15)
    long = pd.concat([
        pd.DataFrame({"country": top15.index, "period": last12_label, "value": top15["now"].values,
                      "share": top15["share_now"].map(lambda v: f"{v:.1f}%").values}),
        pd.DataFrame({"country": top15.index, "period": prev12_label, "value": top15["before"].values,
                      "share": top15["share_before"].map(lambda v: f"{v:.1f}%").values}),
    ])
    st.altair_chart(charts.grouped_bars(
        long, "country", "period", "value", "Top 15 partners: latest 12 months vs the 12 months before",
        cat_order=list(top15.index), group_order=[last12_label, prev12_label],
        colors={last12_label: charts.SERIES[0], prev12_label: charts.OTHER},
        extra_tooltip=[alt.Tooltip("share:N", title="Share of total")]), use_container_width=True)

    st.dataframe(pd.DataFrame({
        f"Latest 12 months": p["now"].map(fmt_usd),
        f"12 months before": p["before"].map(fmt_usd),
        "Growth": p["growth"].map(fmt_pct),
        "Share of total": p["share_now"].map(lambda v: f"{v:.1f}%"),
        "Change in share": p["share_shift"].map(fmt_pts),
    }).rename_axis("Country"), use_container_width=True)
    st.caption("Share of total = this country's part of all Indonesian "
               f"{flow_name.lower()}. Change in share is in percentage points: +1.0 pts means "
               "the country's share grew by one point, e.g. from 10% to 11%.")

    ctry = st.selectbox(f"Look at one country", p.index.tolist())
    sub = fw[fw.country == ctry]
    g = db.monthly_series(sub, by="product_group")
    topg = sub.groupby("product_group")["value_usd"].sum().sort_values(ascending=False)
    keep = topg.head(7).index.tolist()
    g["group"] = g["product_group"].where(g["product_group"].isin(keep), "Other")
    g = g.groupby(["period", "group"], as_index=False)["value_usd"].sum()
    st.altair_chart(charts.stacked_bars(
        g.rename(columns={"group": "product_group"}), "product_group",
        f"{flow_name} {'to' if flow == 'export' else 'from'} {ctry}, by product group",
        order=keep + ["Other"]), use_container_width=True)

# ---------- Import demand ----------
with tab_demand:
    st.caption("Imports split by end use. **Approximate:** mapped from HS chapters, so machinery "
               "and electronics count as capital goods even though they include parts. "
               "Rising capital goods usually signal investment; raw materials signal factory "
               "activity; consumer goods signal household demand.")
    imp = df[(df.flow == "import") & (df.period <= month)]
    s = db.monthly_series(imp, by="import_use")
    order = ["Raw materials & intermediates", "Capital goods", "Consumer goods", "Fuels"]
    snap = s[s.period == month].set_index("import_use")
    cols = st.columns(4)
    for c, u in zip(cols, order):
        if u in snap.index:
            c.metric(u, fmt_usd(snap.loc[u, "value_usd"]),
                     fmt_pct(snap.loc[u, "roll3_yoy_pct"]) + " 3-month trend")
    present = [u for u in order if u in set(s["import_use"])]
    st.altair_chart(charts.line_focus(s[s.period > start], "roll3_yoy_pct", "import_use",
                                      "Momentum by end use: last 3 months vs a year earlier",
                                      order=present, value_title="3-month change"),
                    use_container_width=True)
    st.altair_chart(charts.line_focus(s[s.period > start], "value_usd", "import_use",
                                      "Monthly imports by end use", order=present),
                    use_container_width=True)
