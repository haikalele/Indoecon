"""Altair chart builders with the hover styles picked in the style lab:

* Bars "C": the bar under the pointer gets an outline and the others fade.
* Lines "C": the line nearest the pointer stays bold, the others fade, and a dot plus
  tooltip mark the exact point.
"""
from __future__ import annotations

import altair as alt
import pandas as pd

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#9a9890"
NEG = "#eb6834"
OUTLINE = "#15191e"

_B_AXIS = alt.Axis(format="$.2~s", labelExpr="replace(datum.label, 'G', 'B')", title=None, tickCount=6)
_PCT_AXIS = alt.Axis(format="+.0f", labelExpr="datum.label + '%'", title=None)


def _usd(v) -> str:
    if v is None or pd.isna(v):
        return "n/a"
    s, a = ("-" if v < 0 else ""), abs(v)
    if a >= 1e9:
        return f"{s}${a/1e9:,.2f}B"
    if a >= 1e6:
        return f"{s}${a/1e6:,.0f}M"
    return f"{s}${a/1e3:,.0f}K"


def _pct(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:+.1f}%"


def _scale(domain: list, colors: dict | None = None) -> alt.Scale:
    if colors:
        return alt.Scale(domain=domain, range=[colors[d] for d in domain])
    return alt.Scale(domain=domain, range=(SERIES * 2)[:len(domain)])


def line_focus(df: pd.DataFrame, y: str, color: str, title: str, *, order: list | None = None,
               colors: dict | None = None, value_title: str = "Value", height: int = 340) -> alt.LayerChart:
    """Lines "C". `y` is a USD column, or a percent column whose name ends in `_pct`."""
    is_pct = y.endswith("_pct")
    d = df.dropna(subset=[y])[["period", color, y]].copy()
    d["label"] = d[y].map(_pct if is_pct else _usd)
    order = order or list(d.groupby(color)[y].sum().sort_values(ascending=False).index)
    near = alt.selection_point(name="near", fields=[color, "period"], nearest=True,
                               on="pointermove", clear="pointerout")
    focus = alt.selection_point(name="focus", fields=[color], nearest=True,
                                on="pointermove", clear="pointerout")
    base = alt.Chart(d).encode(
        x=alt.X("period:T", axis=alt.Axis(format="%b %y", grid=False, title=None)),
        y=alt.Y(f"{y}:Q", axis=_PCT_AXIS if is_pct else _B_AXIS, scale=alt.Scale(zero=False)),
        color=alt.Color(f"{color}:N", scale=_scale(order, colors), sort=order,
                        legend=alt.Legend(title=None, orient="top", labelLimit=220)),
    )
    # Invisible hover targets: opacity set in the encoding so no theme can override it.
    hit = base.mark_circle(size=300).encode(
        opacity=alt.value(0),
        tooltip=[alt.Tooltip(f"{color}:N", title=color.replace("_", " ").capitalize()),
                 alt.Tooltip("period:T", format="%b %Y", title="Month"),
                 alt.Tooltip("label:N", title=value_title)]).add_params(near, focus)
    lines = base.mark_line(interpolate="monotone").encode(
        opacity=alt.condition(focus, alt.value(1), alt.value(0.18), empty=True),
        strokeWidth=alt.condition(focus, alt.value(3), alt.value(2), empty=False))
    # The dot layer only gets the hovered row; at rest it has no data, so nothing can show.
    dot = base.mark_circle(size=90, stroke="white", strokeWidth=2, opacity=1).transform_filter(
        {"param": "near", "empty": False})
    layers = [lines, hit, dot]
    if is_pct:
        zero = alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(color="gray", opacity=.6).encode(y="z:Q")
        layers.insert(0, zero)
    return alt.layer(*layers).properties(title=title, height=height)


def grouped_bars(df: pd.DataFrame, cat: str, group: str, value: str, title: str, *, cat_order: list,
                 group_order: list, colors: dict, extra_tooltip: list | None = None,
                 height: int = 520) -> alt.Chart:
    """Bars "C" for side-by-side bars (partners: latest 12 months vs the 12 before)."""
    d = df.copy()
    d["label"] = d[value].map(_usd)
    hov = alt.selection_point(name="hov", on="pointerover", clear="pointerout")
    tips = [alt.Tooltip(f"{cat}:N", title=cat.capitalize()), alt.Tooltip(f"{group}:N", title="Period"),
            alt.Tooltip("label:N", title="Value")] + (extra_tooltip or [])
    return alt.Chart(d).mark_bar(cornerRadiusEnd=3, strokeWidth=2).encode(
        y=alt.Y(f"{cat}:N", sort=cat_order, axis=alt.Axis(title=None, labelLimit=160)),
        yOffset=alt.YOffset(f"{group}:N", sort=group_order),
        x=alt.X(f"{value}:Q", axis=_B_AXIS),
        color=alt.Color(f"{group}:N", scale=_scale(group_order, colors), sort=group_order,
                        legend=alt.Legend(title=None, orient="top")),
        opacity=alt.condition(hov, alt.value(1), alt.value(0.3), empty=True),
        stroke=alt.condition(hov, alt.value(OUTLINE), alt.value(None), empty=False),
        tooltip=tips,
    ).add_params(hov).properties(title=title, height=height)


def diverging_bars(df: pd.DataFrame, cat: str, *, tooltip: list, height: int = 380) -> alt.Chart:
    """Bars "C" for Biggest movers: increases blue, decreases orange. Needs `change_usd`."""
    d = df.copy()
    d["direction"] = (d["change_usd"] >= 0).map({True: "Up", False: "Down"})
    hov = alt.selection_point(name="hov", on="pointerover", clear="pointerout")
    return alt.Chart(d).mark_bar(cornerRadiusEnd=3, strokeWidth=2).encode(
        y=alt.Y(f"{cat}:N", sort=list(d[cat]), axis=alt.Axis(title=None, labelLimit=160)),
        x=alt.X("change_usd:Q", axis=alt.Axis(format="$.2~s", labelExpr="replace(datum.label, 'G', 'B')",
                                               title=None)),
        color=alt.Color("direction:N", scale=alt.Scale(domain=["Up", "Down"], range=[SERIES[0], NEG]),
                        legend=None),
        opacity=alt.condition(hov, alt.value(1), alt.value(0.3), empty=True),
        stroke=alt.condition(hov, alt.value(OUTLINE), alt.value(None), empty=False),
        tooltip=tooltip,
    ).add_params(hov).properties(height=height)


def stacked_bars(df: pd.DataFrame, color: str, title: str, *, order: list, height: int = 400) -> alt.Chart:
    """Bars "C" for monthly stacked bars: the hovered segment is outlined, others fade."""
    d = df.copy()
    d["label"] = d["value_usd"].map(_usd)
    d["rank"] = d[color].map({k: i for i, k in enumerate(order)})
    hov = alt.selection_point(name="hov", on="pointerover", clear="pointerout")
    colors = (SERIES[:len(order) - 1] + [OTHER]) if order and order[-1] == "Other" else SERIES[:len(order)]
    return alt.Chart(d).mark_bar(strokeWidth=2).encode(
        x=alt.X("yearmonth(period):O", axis=alt.Axis(format="%b %y", title=None, labelAngle=0,
                                                       labelOverlap="parity")),
        y=alt.Y("value_usd:Q", stack="zero", axis=_B_AXIS),
        color=alt.Color(f"{color}:N", sort=order, scale=alt.Scale(domain=order, range=colors),
                        legend=alt.Legend(title=None, orient="top", labelLimit=220)),
        order=alt.Order("rank:Q"),
        opacity=alt.condition(hov, alt.value(1), alt.value(0.35), empty=True),
        stroke=alt.condition(hov, alt.value(OUTLINE), alt.value(None), empty=False),
        tooltip=[alt.Tooltip(f"{color}:N", title="Product group"),
                 alt.Tooltip("period:T", format="%b %Y", title="Month"),
                 alt.Tooltip("label:N", title="Value")],
    ).add_params(hov).properties(title=title, height=height)


def momentum_heatmap(df: pd.DataFrame, title: str, *, order: list, height: int | None = None) -> alt.Chart:
    """Product group x month for the 3-month change vs a year earlier (roll3_yoy_pct).
    Blue = growth, orange = decline. The size of the change sets the opacity, so "about flat"
    is fully transparent and blends into the page background in light and dark mode."""
    d = df.dropna(subset=["roll3_yoy_pct"])[["period", "product_group", "roll3_yoy_pct"]].copy()
    d["label"] = d["roll3_yoy_pct"].map(_pct)
    d["direction"] = (d["roll3_yoy_pct"] >= 0).map({True: "Growing", False: "Shrinking"})
    d["size"] = d["roll3_yoy_pct"].abs().clip(upper=25)
    # Orange reads weaker than blue on white, so declines get a deeper red-orange and a
    # 1.4x opacity boost to look equally strong.
    boost = d["direction"].map({"Growing": 1.0, "Shrinking": 1.4})
    d["strength"] = (d["size"] / 25 * boost).clip(upper=1)
    hov = alt.selection_point(name="hov", on="pointerover", clear="pointerout")
    return alt.Chart(d).mark_rect(cornerRadius=2).encode(
        x=alt.X("yearmonth(period):O", scale=alt.Scale(paddingInner=0.1),
                axis=alt.Axis(format="%b %y", title=None, labelAngle=0, labelOverlap="parity")),
        y=alt.Y("product_group:N", sort=order, scale=alt.Scale(paddingInner=0.1),
                axis=alt.Axis(title=None, labelLimit=200)),
        color=alt.Color("direction:N", scale=alt.Scale(domain=["Growing", "Shrinking"], range=[SERIES[0], "#d03a1c"]),
                        legend=alt.Legend(title=None, orient="bottom")),
        opacity=alt.Opacity("strength:Q", scale=alt.Scale(domain=[0, 1], range=[0, 1]),
                            legend=None),
        stroke=alt.condition(hov, alt.value("#888888"), alt.value(None), empty=False),
        strokeWidth=alt.condition(hov, alt.value(2), alt.value(0), empty=False),
        tooltip=[alt.Tooltip("product_group:N", title="Product group"),
                 alt.Tooltip("period:T", format="%b %Y", title="Month"),
                 alt.Tooltip("label:N", title="3-month change vs a year earlier")],
    ).add_params(hov).properties(title=title, height=alt.Step(26))


def destination_mix(df: pd.DataFrame, title: str, *, country_order: list, group_order: list) -> alt.Chart:
    """One horizontal bar per partner country, split by product group (Bars "C" hover).
    Expects columns country, product_group, value_usd."""
    d = df.copy()
    d["label"] = d["value_usd"].map(_usd)
    tot = d.groupby("country")["value_usd"].transform("sum")
    d["share"] = (d["value_usd"] / tot * 100).map(lambda v: f"{v:.0f}% of this country")
    d["total"] = tot.map(_usd)
    d["rank"] = d["product_group"].map({k: i for i, k in enumerate(group_order)})
    hov = alt.selection_point(name="hov", on="pointerover", clear="pointerout")
    colors = (SERIES[:len(group_order) - 1] + [OTHER]) if group_order[-1] == "Other" else SERIES[:len(group_order)]
    return alt.Chart(d).mark_bar(strokeWidth=2).encode(
        y=alt.Y("country:N", sort=country_order, axis=alt.Axis(title=None, labelLimit=160)),
        x=alt.X("value_usd:Q", stack="zero", axis=alt.Axis(format="$.2~s", labelExpr="replace(datum.label, 'G', 'B')",
                                                             title=None, orient="top", tickCount=6)),
        color=alt.Color("product_group:N", sort=group_order, scale=alt.Scale(domain=group_order, range=colors),
                        legend=alt.Legend(title=None, orient="top", labelLimit=220, columns=4)),
        order=alt.Order("rank:Q"),
        opacity=alt.condition(hov, alt.value(1), alt.value(0.35), empty=True),
        stroke=alt.condition(hov, alt.value(OUTLINE), alt.value(None), empty=False),
        tooltip=[alt.Tooltip("country:N", title="Country"), alt.Tooltip("product_group:N", title="Product group"),
                 alt.Tooltip("label:N", title="Value"), alt.Tooltip("share:N", title="Share"),
                 alt.Tooltip("total:N", title="Country total")],
    ).add_params(hov).properties(title=title, height=alt.Step(26))
