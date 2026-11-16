"""Indonesia trade dashboard (Streamlit).  Run:  python -m streamlit run app.py"""
from __future__ import annotations

import altair as alt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.colors import sample_colorscale
import streamlit as st

from econ import charts, db, groups

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


def _signed_usd(x) -> str:
    return fmt_usd(x) if x is None or pd.isna(x) or x < 0 else "+" + fmt_usd(x)


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


def treemap(data: pd.DataFrame, path: list[str], title: str, height: int = 420,
            root_label: str = "All") -> go.Figure:
    """Plotly ignores root_color here and paints the root dark grey, so we add our own root
    and colour every box explicitly, with the root transparent."""
    d = data.assign(_root=root_label)
    fig = px.treemap(d, path=["_root"] + path, values="value_usd", color="value_usd",
                     color_continuous_scale=BLUES, title=title)
    tr = fig.data[0]
    vals = [float(v) for v in tr.marker.colors]
    kids = [v for i, v in zip(tr.ids, vals) if i != root_label]
    lo, hi = (min(kids), max(kids)) if kids else (0, 1)
    colors = ["rgba(0,0,0,0)" if i == root_label else
              sample_colorscale(BLUES, [(v - lo) / ((hi - lo) or 1)])[0] for i, v in zip(tr.ids, vals)]
    labels = [fmt_usd(v) for v in tr.values]
    fig.update_traces(marker=dict(colors=colors, colorscale=None), pathbar=dict(visible=False),
                      customdata=[[l] for l in labels],
                      texttemplate="%{label}<br>%{percentRoot:.1%}",
                      hovertemplate="<b>%{label}</b><br>%{customdata[0]}<br>"
                                    "%{percentRoot:.1%} of total<extra></extra>")
    if len(path) == 1:   # flat treemap: no header band for the root at all
        fig.update_traces(marker_pad=dict(t=0, l=0, r=0, b=0))
    fig.update_coloraxes(showscale=False)
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
    present_prov = set(df.province)
    region_opts = ["Indonesia"]
    for g, provs in groups.ISLAND_GROUPS.items():   # each island group, then its provinces
        if g in set(df.island):
            region_opts += [g] + [p for p in provs if p in present_prov]
    r1, _ = st.columns([1, 1])
    region = r1.selectbox("Region", region_opts, key="ov_region",
                          format_func=lambda r: r if r == "Indonesia" or r in groups.ISLAND_GROUPS
                          else f"\u2003\u2003{r}",   # em spaces: an indent the browser keeps
                          help="Indonesia = whole country. Each island group is followed by its provinces "
                               "(by port of loading / unloading).")
    if region == "Indonesia":
        dfr, sub_col = df, "island"
    elif region in groups.ISLAND_GROUPS:
        dfr, sub_col = df[df.island == region], "province"
    else:
        dfr, sub_col = df[df.province == region], "port"
    fr = dfr[dfr.flow == flow]
    fwr = fr[(fr.period > start) & (fr.period <= month)]
    where = "" if region == "Indonesia" else f" · {region}"

    tot = db.monthly_series(dfr[dfr.period <= month], by="flow")
    tot["flow"] = tot["flow"].map(FLOW_NAME)
    cur = tot[tot.period == month].set_index("flow")
    exp_v = cur["value_usd"].get("Exports", 0)
    imp_v = cur["value_usd"].get("Imports", 0)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"Exports{where}", fmt_usd(exp_v), fmt_pct(cur["yoy_pct"].get("Exports")) + " YoY")
    k2.metric(f"Imports{where}", fmt_usd(imp_v), fmt_pct(cur["yoy_pct"].get("Imports")) + " YoY")
    def _bal(w):
        return w[w.flow == "export"].value_usd.sum() - w[w.flow == "import"].value_usd.sum()
    ago = month - pd.DateOffset(years=1)
    bal, bal_ago = _bal(dfr[dfr.period == month]), _bal(dfr[dfr.period == ago])
    k3.metric("Trade balance", fmt_usd(bal), _signed_usd(bal - bal_ago) + f" vs {ago:%b %Y}",
              help=f"Exports minus imports. {ago:%b %Y}: {fmt_usd(bal_ago)}")
    ytd_bal = _bal(dfr[(dfr.period.dt.year == month.year) & (dfr.period <= month)])
    ytd_ago = _bal(dfr[(dfr.period.dt.year == ago.year) & (dfr.period <= ago)])
    k4.metric(f"Balance YTD {month.year}", fmt_usd(ytd_bal),
              _signed_usd(ytd_bal - ytd_ago) + f" vs Jan–{ago:%b %Y}",
              help=f"Jan–{ago:%b %Y}: {fmt_usd(ytd_ago)}")

    # One-line "what happened" for the selected flow
    mv = db.movers(fr, "product_group", month, min_base_usd=0, top=1000)
    if not mv.empty and mv.year_ago.sum() > 0:
        now_t, ago_t = mv.this_month.sum(), mv.year_ago.sum()
        ups = mv[mv.change_usd > 0].nlargest(2, "change_usd")
        downs = mv[mv.change_usd < 0].nsmallest(1, "change_usd")
        fmt_mv = lambda m: ", ".join(f"{r.product_group} ({_signed_usd(r.change_usd)})" for r in m.itertuples())
        line = (f"**{flow_name}{where}** in {month:%b %Y}: **{fmt_usd(now_t)}**, "
                f"**{fmt_pct((now_t / ago_t - 1) * 100)}** vs {ago:%b %Y} ({_signed_usd(now_t - ago_t)}).")
        if not ups.empty:
            line += f" Biggest gains: {fmt_mv(ups)}."
        if not downs.empty:
            line += f" Biggest drag: {fmt_mv(downs)}."
        st.info(line, icon="📌")
    if region != "Indonesia":
        nat = df[(df.period >= last12_start) & (df.period <= month)].groupby("flow")["value_usd"].sum()
        reg = dfr[(dfr.period >= last12_start) & (dfr.period <= month)].groupby("flow")["value_usd"].sum()
        sh = lambda fl: reg.get(fl, 0) / nat.get(fl, 1) * 100
        st.markdown(f"{region} handles **{sh('export'):.1f}%** of Indonesia's exports and "
                    f"**{sh('import'):.1f}%** of its imports ({last12_label}).")

    t = tot[tot.period > start]
    def value_chart(h=340):
        return charts.line_focus(t, "value_usd", "flow", f"Monthly value{where}",
                                 order=["Exports", "Imports"], colors=FLOW_COLOR, height=h)
    def momentum_chart(h=340):
        return charts.line_focus(t, "roll3_yoy_pct", "flow",
                                 "Momentum: last 3 months vs same 3 months a year earlier",
                                 order=["Exports", "Imports"], colors=FLOW_COLOR,
                                 value_title="3-month change", height=h)
    comp = fr[(fr.period >= last12_start) & (fr.period <= month)]
    comp = comp.groupby("product_group", as_index=False)["value_usd"].sum()
    def mix_chart(h=420):
        return treemap(comp, ["product_group"], f"{flow_name} by product group, {last12_label}", height=h)
    heat = db.monthly_series(fwr, by="product_group")
    heat = heat[heat.period > start]
    by_size = comp.set_index("product_group")["value_usd"].sort_values(ascending=False)
    heat_order = [g for g in by_size.index if by_size[g] > 0]
    def heat_chart():
        return charts.momentum_heatmap(heat[heat.product_group.isin(heat_order)],
                                       f"{flow_name} momentum by product group{where}", order=heat_order)
    heat_note = ("Each cell compares the latest 3 months with the same 3 months a year earlier. "
                 "Blue = growing, orange = shrinking; stronger colour = bigger change "
                 "(empty = about flat, full colour = 25% or more).")

    def _trend_style(v):
        """Same colours as the heatmap: blue growing, red-orange shrinking, stronger = bigger."""
        if v is None or pd.isna(v):
            return ""
        a = min(abs(v) / 25 * (1.0 if v >= 0 else 1.4), 1) * 0.85
        rgb = "42,120,214" if v >= 0 else "208,58,28"
        txt = "color: white;" if a > 0.55 else ""
        return f"background-color: rgba({rgb},{a:.2f}); {txt}"

    def breakdown():
        """Inside the chosen region: islands (for Indonesia), provinces (island) or ports (province)."""
        sname = {"island": "Island group", "province": "Province", "port": "Port"}[sub_col]
        ss = db.monthly_series(fwr, by=sub_col)
        l12 = fr[(fr.period >= last12_start) & (fr.period <= month)].groupby(sub_col)["value_usd"].sum()
        l12 = l12.sort_values(ascending=False).head(12)
        snap = ss[ss.period == month].set_index(sub_col)
        tb = pd.DataFrame({"Last 12 months": l12.map(fmt_usd),
                           "Share": (l12 / max(l12.sum(), 1) * 100).map(lambda v: f"{v:.1f}%"),
                           "3-month trend vs a year ago": snap["roll3_yoy_pct"].reindex(l12.index)})
        cfg = {"3-month trend vs a year ago": st.column_config.NumberColumn(format="%+.1f%%")}
        st.markdown(f"**{flow_name} by {sname.lower()}{where}** · {last12_label}")
        styled = tb.rename_axis(sname).style.map(_trend_style, subset=["3-month trend vs a year ago"])
        st.dataframe(styled, column_config=cfg, use_container_width=True)

    a1, a2 = st.columns(2)
    a1.altair_chart(value_chart(300), use_container_width=True)
    a2.altair_chart(momentum_chart(300), use_container_width=True)
    other = "Imports" if flow == "export" else "Exports"
    st.markdown(f"#### {flow_name} detail{where}")
    st.caption(f"Everything below shows {flow_name.lower()} only. Switch to {other} with the Flow "
               "buttons at the top.")
    b1, b2 = st.columns([2, 3])
    b1.plotly_chart(mix_chart(520), use_container_width=True)
    b2.altair_chart(heat_chart(), use_container_width=True)
    b2.caption(heat_note)
    breakdown()

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

    st.markdown(f"**Where goods from {port_sel} go**" if flow == "export" else f"**Where goods into {port_sel} come from**")
    dsub = sub.groupby(["country", "product_group"], as_index=False)["value_usd"].sum()
    if not dsub.empty:
        c_tot = dsub.groupby("country")["value_usd"].sum().sort_values(ascending=False)
        n_pages = (len(c_tot) - 1) // 10 + 1
        page_key = f"dest_page::{flow}::{level}::{port_sel}"   # new port/flow starts at page 1
        st.session_state.setdefault(page_key, 0)

        def _turn(step: int, key=page_key, last=n_pages - 1):
            st.session_state[key] = max(0, min(st.session_state[key] + step, last))

        page = max(0, min(st.session_state[page_key], n_pages - 1))
        countries = list(c_tot.index[page * 10:(page + 1) * 10])
        first, last_n = page * 10 + 1, page * 10 + len(countries)
        head, nav = st.columns([0.78, 0.22], vertical_alignment="center")
        head.markdown(f"**{partner_word.capitalize()} countries, then product group** · {last12_label}")
        n1, n2, n3 = nav.columns([1, 2.2, 1], vertical_alignment="center", gap="small")
        n1.button("◀", disabled=page == 0, key="dest_prev", help="Previous 10 countries",
                  on_click=_turn, args=(-1,))
        n2.markdown(f"<div style='text-align:center;font-size:0.9em;white-space:nowrap'>"
                    f"{first}–{last_n} of {len(c_tot)}</div>", unsafe_allow_html=True)
        n3.button("▶", disabled=page >= n_pages - 1, key="dest_next", help="Next 10 countries",
                  on_click=_turn, args=(1,))
        fig = treemap(dsub[dsub.country.isin(countries)], ["country", "product_group"], "", height=520)
        fig.update_layout(margin=dict(l=0, r=0, t=4, b=0))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Box size = value over the last 12 months. Click a country to zoom into its products; "
                   "click the top bar to zoom back out.")

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

    # Headline numbers for the chosen country
    row = p.loc[ctry]
    rank = p.index.get_loc(ctry) + 1
    cm = f[(f.country == ctry) & (f.period <= month)]
    m_now = cm[cm.period == month].value_usd.sum()
    m_ago = cm[cm.period == month - pd.DateOffset(years=1)].value_usd.sum()
    both = df[df.country == ctry]
    def _bal(a, b):
        w = both[(both.period >= a) & (both.period <= b)]
        return w[w.flow == "export"].value_usd.sum() - w[w.flow == "import"].value_usd.sum()
    bal_now, bal_before = _bal(last12_start, month), _bal(prev12_start, prev12_end)
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Last 12 months", fmt_usd(row["now"]),
              (fmt_pct(row["growth"]) + " vs 12 months before") if pd.notna(row["growth"]) else None,
              help=f"{flow_name} {'to' if flow == 'export' else 'from'} {ctry}, {last12_label}")
    h2.metric(f"Share of {flow_name.lower()}", f"{row['share_now']:.1f}%",
              fmt_pts(row["share_shift"]), help=f"#{rank} of {len(p)} partners")
    h3.metric(f"{month:%b %Y}", fmt_usd(m_now),
              (fmt_pct((m_now / m_ago - 1) * 100) + " YoY") if m_ago > 0 else None)
    h4.metric("Trade balance, last 12 months", fmt_usd(bal_now),
              fmt_usd(bal_now - bal_before) + " vs 12 months before",
              help="Indonesia's exports to this country minus imports from it. Positive = surplus.")
    pg = sub[sub.period >= last12_start].groupby("product_group")["value_usd"].sum().sort_values(ascending=False)
    if not pg.empty:
        st.markdown(f"#{rank} {partner_word} for Indonesian {flow_name.lower()}. Biggest product group: "
                    f"**{pg.index[0]}** ({pg.iloc[0] / pg.sum() * 100:.0f}% of the last 12 months).")
    g = db.monthly_series(sub, by="product_group")
    topg = sub.groupby("product_group")["value_usd"].sum().sort_values(ascending=False)
    keep = topg.head(7).index.tolist()
    g["group"] = g["product_group"].where(g["product_group"].isin(keep), "Other")
    g = g.groupby(["period", "group"], as_index=False)["value_usd"].sum()
    st.altair_chart(charts.stacked_bars(
        g.rename(columns={"group": "product_group"}), "product_group",
        f"{flow_name} {'to' if flow == 'export' else 'from'} {ctry}, by product group",
        order=keep + ["Other"]), use_container_width=True)

    # Which Indonesian provinces / ports trade with this country
    split = st.radio(f"Split {flow_name.lower()} {'to' if flow == 'export' else 'from'} {ctry} by",
                     ["Province", "Port"], horizontal=True, key="ctry_split")
    lvl = split.lower()
    c_now = f[(f.country == ctry) & (f.period >= last12_start) & (f.period <= month)]
    c_before = f[(f.country == ctry) & (f.period >= prev12_start) & (f.period <= prev12_end)]
    r = pd.DataFrame({"now": c_now.groupby(lvl)["value_usd"].sum(),
                      "before": c_before.groupby(lvl)["value_usd"].sum()}).fillna(0)
    r = r[(r["now"] > 0) | (r["before"] > 0)].sort_values("now", ascending=False)
    if not r.empty:
        top3 = ", ".join(f"**{n}** ({v / max(r['now'].sum(), 1) * 100:.0f}%)" for n, v in r["now"].head(3).items())
        st.markdown(f"Over the last 12 months, {flow_name.lower()} {'to' if flow == 'export' else 'from'} "
                    f"{ctry} mainly go through {top3}.")
        keep_r = r.head(7).index.tolist()
        gr = db.monthly_series(sub, by=lvl)
        gr["grp"] = gr[lvl].where(gr[lvl].isin(keep_r), "Other")
        gr = gr.groupby(["period", "grp"], as_index=False)["value_usd"].sum()
        order_r = keep_r + (["Other"] if (gr["grp"] == "Other").any() else [])
        st.altair_chart(charts.stacked_bars(
            gr.rename(columns={"grp": lvl}), lvl,
            f"{flow_name} {'to' if flow == 'export' else 'from'} {ctry}, by Indonesian "
            f"{'province' if lvl == 'province' else port_word}",
            order=order_r, tip_title=split), use_container_width=True)
        r["growth"] = (r["now"] / r["before"].where(r["before"] > 0) - 1) * 100
        r["share"] = r["now"] / max(r["now"].sum(), 1) * 100
        st.dataframe(pd.DataFrame({
            "Latest 12 months": r["now"].map(fmt_usd),
            "12 months before": r["before"].map(fmt_usd),
            "Growth": r["growth"].map(fmt_pct),
            f"Share of {ctry}": r["share"].map(lambda v: f"{v:.1f}%"),
        }).rename_axis(split), use_container_width=True)
        if lvl == "province" and "Unmapped" in r.index:
            st.caption("'Unmapped' = ports not yet linked to a province in ref/ports_province.csv.")

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
