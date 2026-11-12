"""Indonesia trade dashboard (Streamlit).  Run:  streamlit run app.py"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from econ import db

st.set_page_config(page_title="Indonesia trade signals", layout="wide")

# Categorical palette (fixed order, validated); see README "Chart colours".
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
FLOW_COLOR = {"export": SERIES[0], "import": SERIES[1]}
BLUES = ["#dbe9fa", "#9cc3f0", "#5e9be3", "#2a78d6", "#1a559e"]
GRID = "rgba(128,128,128,0.18)"


def fmt_usd(x: float) -> str:
    if pd.isna(x):
        return "n/a"
    a = abs(x)
    if a >= 1e9:
        return f"${x/1e9:,.2f}B"
    if a >= 1e6:
        return f"${x/1e6:,.0f}M"
    return f"${x:,.0f}"


def fmt_pct(x) -> str:
    return "n/a" if pd.isna(x) else f"{x:+.1f}%"


def style(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=36, b=8), hovermode="x unified",
                      legend=dict(orientation="h", y=1.08, x=0, title=None),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False, title=None)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, title=None)
    fig.update_traces(selector=dict(type="scatter"), line=dict(width=2))
    return fig


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
    st.info("No data yet. Run `python -m econ.fetch --years 2022 2023 2024 2025` "
            "(needs BPS_API_KEY), or `python -m econ.fetch --demo` to try the screens.")
    st.stop()

if meta.get("source") == "DEMO":
    st.warning("**Demo data.** These numbers are synthetic, for trying the screens only. "
               "Load real BPS data with `python -m econ.fetch`.", icon="⚠️")
st.caption(f"Source: {meta.get('source')} · refreshed {meta.get('refreshed_at')} · "
           "values in USD, FOB for exports and CIF for imports")

# ---------- global filters (one row) ----------
latest = df.period.max()
c1, c2, c3 = st.columns([1, 1, 2])
flow = c1.radio("Flow", ["export", "import"], horizontal=True, format_func=str.title)
month = c2.selectbox("Month", sorted(df.period.unique(), reverse=True),
                     format_func=lambda d: pd.Timestamp(d).strftime("%b %Y"))
month = pd.Timestamp(month)
yrs = c3.slider("Chart window (years)", 1, 10, 3)
start = month - pd.DateOffset(years=yrs)

f = df[df.flow == flow]
fw = f[(f.period > start) & (f.period <= month)]
partner_word = "destination" if flow == "export" else "origin"
port_word = "port of loading" if flow == "export" else "port of unloading"

tab_over, tab_move, tab_port, tab_partner, tab_demand = st.tabs(
    ["Overview", "Biggest movers", "Ports & regions", "Partners", "Import demand"])

# ---------- Overview ----------
with tab_over:
    tot = db.monthly_series(df[df.period <= month], by="flow")
    cur = tot[tot.period == month].set_index("flow")
    exp_v = cur["value_usd"].get("export", 0)
    imp_v = cur["value_usd"].get("import", 0)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Exports", fmt_usd(exp_v), fmt_pct(cur["yoy_pct"].get("export")) + " YoY")
    k2.metric("Imports", fmt_usd(imp_v), fmt_pct(cur["yoy_pct"].get("import")) + " YoY")
    k3.metric("Trade balance", fmt_usd(exp_v - imp_v))
    ytd = df[(df.period.dt.year == month.year) & (df.period <= month)]
    ytd_bal = ytd[ytd.flow == "export"].value_usd.sum() - ytd[ytd.flow == "import"].value_usd.sum()
    k4.metric(f"Balance YTD {month.year}", fmt_usd(ytd_bal))

    t = tot[tot.period > start]
    fig = px.line(t, x="period", y="value_usd", color="flow", color_discrete_map=FLOW_COLOR,
                  title="Monthly value")
    st.plotly_chart(style(fig), use_container_width=True)

    fig = px.line(t.dropna(subset=["roll3_yoy_pct"]), x="period", y="roll3_yoy_pct", color="flow",
                  color_discrete_map=FLOW_COLOR, title="Momentum: 3-month rolling, % change YoY")
    fig.add_hline(y=0, line_color="gray", line_width=1)
    st.plotly_chart(style(fig), use_container_width=True)

    comp = fw[fw.period > month - pd.DateOffset(months=12)]
    comp = comp.groupby("product_group", as_index=False)["value_usd"].sum()
    fig = px.treemap(comp, path=["product_group"], values="value_usd",
                     color="value_usd", color_continuous_scale=BLUES,
                     title=f"{flow.title()} composition, last 12 months")
    fig.update_coloraxes(showscale=False)
    fig.update_traces(texttemplate="%{label}<br>%{percentRoot:.1%}")
    st.plotly_chart(style(fig, 420), use_container_width=True)

# ---------- Movers ----------
with tab_move:
    st.caption(f"{month:%B %Y} vs {month - pd.DateOffset(years=1):%B %Y}, ranked by USD change. "
               "Categories under $5M in both months are hidden.")
    cols = st.columns(3)
    for col, (by, label) in zip(cols, [("product_group", "Product group"),
                                        ("port", port_word.capitalize()),
                                        ("country", f"Partner ({partner_word})")]):
        m = db.movers(f, by, month)
        col.subheader(label)
        if m.empty:
            col.write("No comparison available for this month.")
            continue
        m = m.iloc[::-1]
        fig = go.Figure(go.Bar(
            x=m.change_usd, y=m[by], orientation="h",
            marker_color=[SERIES[0] if v >= 0 else SERIES[1] for v in m.change_usd],
            customdata=list(zip(m.this_month.map(fmt_usd), m.year_ago.map(fmt_usd),
                                m.change_pct.map(fmt_pct))),
            hovertemplate="%{y}<br>Change %{x:$,.3s}<br>Now %{customdata[0]} · "
                          "year ago %{customdata[1]} (%{customdata[2]})<extra></extra>"))
        fig = style(fig, 380)
        fig.update_layout(hovermode="closest")
        col.plotly_chart(fig, use_container_width=True)
        col.dataframe(m.iloc[::-1].assign(
            this_month=lambda d: d.this_month.map(fmt_usd), year_ago=lambda d: d.year_ago.map(fmt_usd),
            change_usd=lambda d: d.change_usd.map(fmt_usd), change_pct=lambda d: d.change_pct.map(fmt_pct)),
            hide_index=True, use_container_width=True)

# ---------- Ports & regions ----------
with tab_port:
    level = st.radio("Group by", ["province", "port"], horizontal=True, format_func=str.title)
    s = db.monthly_series(fw, by=level)
    last12 = fw[fw.period > month - pd.DateOffset(months=12)].groupby(level)["value_usd"].sum()
    top = last12.sort_values(ascending=False).head(8).index.tolist()
    snap = s[s.period == month].set_index(level)
    table = pd.DataFrame({
        "Last 12 months": last12, f"{month:%b %Y}": snap["value_usd"],
        "YoY": snap["yoy_pct"], "3m rolling YoY": snap["roll3_yoy_pct"],
    }).sort_values("Last 12 months", ascending=False)
    st.dataframe(table.style.format({"Last 12 months": fmt_usd, f"{month:%b %Y}": fmt_usd,
                                     "YoY": fmt_pct, "3m rolling YoY": fmt_pct}),
                 use_container_width=True)
    if (fw.province == "Unmapped").any() and level == "province":
        st.caption("'Unmapped' = ports not yet in ref/ports_province.csv; add them there.")
    pick = st.multiselect(f"Compare {level}s (3-month rolling)", sorted(s[level].unique()),
                          default=top[:4], max_selections=8)
    if pick:
        order = [p for p in top if p in pick] + [p for p in pick if p not in top]
        fig = px.line(s[s[level].isin(pick)].dropna(subset=["roll3"]), x="period", y="roll3",
                      color=level, category_orders={level: order},
                      color_discrete_sequence=SERIES, title="3-month rolling value")
        st.plotly_chart(style(fig), use_container_width=True)
    port_sel = st.selectbox(f"What moves through a {level}?", top or sorted(s[level].unique()))
    sub = fw[(fw[level] == port_sel) & (fw.period > month - pd.DateOffset(months=12))]
    mix = sub.groupby(["product_group", "country"], as_index=False)["value_usd"].sum()
    fig = px.treemap(mix, path=["product_group", "country"], values="value_usd",
                     color="value_usd", color_continuous_scale=BLUES,
                     title=f"{port_sel}: product group → {partner_word}, last 12 months")
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(style(fig, 420), use_container_width=True)

# ---------- Partners ----------
with tab_partner:
    s = db.monthly_series(fw, by="country")
    last12 = fw[fw.period > month - pd.DateOffset(months=12)].groupby("country")["value_usd"].sum()
    prev12 = f[(f.period > month - pd.DateOffset(months=24)) &
               (f.period <= month - pd.DateOffset(months=12))].groupby("country")["value_usd"].sum()
    share = pd.DataFrame({"Last 12m": last12, "Prior 12m": prev12}).fillna(0)
    share["Share now"] = share["Last 12m"] / share["Last 12m"].sum() * 100
    share["Share before"] = share["Prior 12m"] / max(share["Prior 12m"].sum(), 1) * 100
    share["Share shift (pts)"] = share["Share now"] - share["Share before"]
    share = share.sort_values("Last 12m", ascending=False)
    st.dataframe(share.style.format({"Last 12m": fmt_usd, "Prior 12m": fmt_usd,
                                     "Share now": "{:.1f}%", "Share before": "{:.1f}%",
                                     "Share shift (pts)": "{:+.1f}"}), use_container_width=True)
    ctry = st.selectbox(f"Partner ({partner_word})", share.index.tolist())
    sub = fw[fw.country == ctry]
    g = db.monthly_series(sub, by="product_group")
    topg = sub.groupby("product_group")["value_usd"].sum().sort_values(ascending=False)
    keep = topg.head(7).index.tolist()
    g["group"] = g["product_group"].where(g["product_group"].isin(keep), "Other")
    g = g.groupby(["period", "group"], as_index=False)["value_usd"].sum()
    fig = px.bar(g, x="period", y="value_usd", color="group",
                 category_orders={"group": keep + ["Other"]},
                 color_discrete_sequence=SERIES[:len(keep)] + ["#9a9890"],
                 title=f"{flow.title()} with {ctry} by product group")
    fig.update_traces(marker_line_width=0)
    fig.update_layout(bargap=0.15)
    st.plotly_chart(style(fig, 400), use_container_width=True)

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
                     fmt_pct(snap.loc[u, "roll3_yoy_pct"]) + " 3m YoY")
    fig = px.line(s[(s.period > start)].dropna(subset=["roll3_yoy_pct"]), x="period",
                  y="roll3_yoy_pct", color="import_use", category_orders={"import_use": order},
                  color_discrete_sequence=SERIES, title="Momentum by end use: 3-month rolling, % YoY")
    fig.add_hline(y=0, line_color="gray", line_width=1)
    st.plotly_chart(style(fig), use_container_width=True)
