"""Plotly chart builders: price chart (4 views), sparklines, gauges, bars.

Visual rules (applied everywhere):
- Dark theme (plotly_dark) with recessive grid and muted ink.
- Performance/Area views split the series at the baseline: green above, red
  below, with linearly interpolated crossing points so segments never bleed
  across the baseline.
- For 1D charts the baseline must be YESTERDAY'S CLOSE — pass baseline_price.
  Otherwise overnight gaps make an up-looking chart on a down day.
- One y-axis per panel, never a dual axis: volume renders in its own subplot.
- End-of-period return shown as a colored badge anchored at the last point.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Polarity colors (finance convention) + chrome ink on the dark surface.
UP = "#34d399"
DOWN = "#f87171"
UP_FILL = "rgba(52, 211, 153, 0.18)"
DOWN_FILL = "rgba(248, 113, 113, 0.18)"
GRID = "#2c2c2a"
INK_MUTED = "#898781"
INK = "#c3c2b7"

# Validated categorical slots (dark mode) for identity encodings (pie, multi-
# series). Fixed order — never cycled, never re-assigned on filter.
CATEGORICAL = [
    "#3987e5", "#008300", "#d55181", "#c98500",
    "#199e70", "#d95926", "#9085e9", "#e66767",
]
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

VIEWS = ["Performance", "Price", "Candlestick", "Area"]


def _layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=8, r=8, t=28, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        hovermode="x unified",
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', color=INK),
        hoverlabel=dict(font_size=13),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, showline=False, tickfont=dict(color=INK_MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, showline=False, tickfont=dict(color=INK_MUTED))
    return fig


def split_traces(x: list, y: list[float], baseline: float) -> tuple[list, list, list, list]:
    """Split a series at `baseline` with interpolated crossing points.

    Returns (x_above, y_above, x_below, y_below) where the "off" side of each
    list carries None gaps, so Plotly draws disconnected green/red segments
    that meet exactly at the baseline.
    """
    x_above: list = []
    y_above: list = []
    x_below: list = []
    y_below: list = []

    def push(side_above: bool, xi, yi) -> None:
        if side_above:
            x_above.append(xi); y_above.append(yi)
            x_below.append(xi); y_below.append(None)
        else:
            x_below.append(xi); y_below.append(yi)
            x_above.append(xi); y_above.append(None)

    prev_x = prev_y = None
    for xi, yi in zip(x, y):
        if yi is None or pd.isna(yi):
            continue
        if prev_y is not None:
            crossed = (prev_y - baseline) * (yi - baseline) < 0
            if crossed:
                t = (baseline - prev_y) / (yi - prev_y)
                try:
                    xc = prev_x + (xi - prev_x) * t
                except TypeError:  # non-arithmetic x (e.g. categorical)
                    xc = xi
                # The crossing point belongs to BOTH sides so segments touch.
                x_above.append(xc); y_above.append(baseline)
                x_below.append(xc); y_below.append(baseline)
        push(yi >= baseline, xi, yi)
        prev_x, prev_y = xi, yi
    return x_above, y_above, x_below, y_below


def _return_badge(fig: go.Figure, x_last, pct: float, row: int | None = None) -> None:
    color = UP if pct >= 0 else DOWN
    fig.add_annotation(
        x=x_last, y=1.0, yref="paper" if row is None else "y domain",
        xanchor="right", yanchor="top",
        text=f"<b>{pct:+.2f}%</b>",
        showarrow=False,
        font=dict(color="#0d0d0d", size=13),
        bgcolor=color, borderpad=4, opacity=0.95,
        row=row, col=1 if row else None,
    )


def render_price_chart(
    df: pd.DataFrame,
    view: str = "Performance",
    baseline_price: float | None = None,
    show_volume: bool = False,
    height: int = 460,
) -> go.Figure | None:
    """Main price chart. `df` is a yfinance OHLCV frame (Close required).

    baseline_price: reference for Performance/Area splits and the return
    badge. For 1D intraday data pass YESTERDAY'S CLOSE; defaults to the first
    close of the window otherwise.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return None

    closes = df["Close"].astype(float)
    x = list(df.index)
    baseline = float(baseline_price) if baseline_price else float(closes.iloc[0])
    if baseline == 0:
        baseline = float(closes.iloc[0]) or 1.0
    pct_series = (closes / baseline - 1.0) * 100.0
    end_pct = float(pct_series.iloc[-1])

    rows = 2 if show_volume else 1
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25] if show_volume else [1.0],
        vertical_spacing=0.03,
    )

    if view == "Performance":
        xa, ya, xb, yb = split_traces(x, list(pct_series), 0.0)
        fig.add_trace(go.Scatter(x=xa, y=ya, mode="lines", line=dict(color=UP, width=2),
                                 name="", hovertemplate="%{y:+.2f}%<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=xb, y=yb, mode="lines", line=dict(color=DOWN, width=2),
                                 name="", hovertemplate="%{y:+.2f}%<extra></extra>"), row=1, col=1)
        fig.add_hline(y=0, line_color=INK_MUTED, line_width=1, line_dash="dot", row=1, col=1)
        fig.update_yaxes(ticksuffix="%", row=1, col=1)
    elif view == "Candlestick":
        needed = {"Open", "High", "Low", "Close"}
        if not needed.issubset(df.columns):
            return render_price_chart(df, "Price", baseline_price, show_volume, height)
        fig.add_trace(go.Candlestick(
            x=x, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            increasing_line_color=UP, decreasing_line_color=DOWN,
            increasing_fillcolor=UP, decreasing_fillcolor=DOWN, name="",
        ), row=1, col=1)
        fig.update_xaxes(rangeslider_visible=False)
        fig.update_layout(hovermode="x")
    elif view == "Area":
        xa, ya, xb, yb = split_traces(x, list(closes), baseline)
        # Fill between an invisible baseline trace and each split half.
        for xs, ys, color, fill in ((xa, ya, UP, UP_FILL), (xb, yb, DOWN, DOWN_FILL)):
            fig.add_trace(go.Scatter(x=xs, y=[baseline] * len(xs), mode="lines",
                                     line=dict(width=0), hoverinfo="skip", showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=2),
                                     fill="tonexty", fillcolor=fill, name="",
                                     hovertemplate="%{y:,.2f}<extra></extra>"), row=1, col=1)
        fig.add_hline(y=baseline, line_color=INK_MUTED, line_width=1, line_dash="dot", row=1, col=1)
    else:  # Price
        fig.add_trace(go.Scatter(x=x, y=list(closes), mode="lines",
                                 line=dict(color=UP if end_pct >= 0 else DOWN, width=2), name="",
                                 hovertemplate="%{y:,.2f}<extra></extra>"), row=1, col=1)
        if baseline_price:
            fig.add_hline(y=baseline, line_color=INK_MUTED, line_width=1, line_dash="dot", row=1, col=1)

    if show_volume and "Volume" in df.columns:
        vol = df["Volume"].fillna(0)
        opens = df["Open"] if "Open" in df.columns else closes.shift(1).fillna(closes)
        colors = [UP if c >= o else DOWN for c, o in zip(closes, opens)]
        fig.add_trace(go.Bar(x=x, y=list(vol), marker_color=colors, opacity=0.45,
                             name="", hovertemplate="%{y:,.0f}<extra></extra>"), row=2, col=1)
        fig.update_yaxes(title_text=None, row=2, col=1)

    _return_badge(fig, x[-1], end_pct)
    return _layout(fig, height)


def render_sparkline(
    df: pd.DataFrame,
    baseline_price: float | None = None,
    height: int = 56,
) -> go.Figure | None:
    """Tiny card sparkline, split green/red at the period baseline.

    For 1D data pass yesterday's close; it is prepended as the first point so
    the overnight gap is part of the picture.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return None
    closes = df["Close"].astype(float)
    x = list(df.index)
    y = list(closes)
    if baseline_price:
        baseline = float(baseline_price)
        try:  # prepend the baseline bar one step before the window opens
            step = x[1] - x[0] if len(x) > 1 else pd.Timedelta(minutes=5)
            x = [x[0] - step] + x
            y = [baseline] + y
        except Exception:
            pass
    else:
        baseline = float(closes.iloc[0])
    xa, ya, xb, yb = split_traces(x, y, baseline)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xa, y=ya, mode="lines", line=dict(color=UP, width=1.5), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=xb, y=yb, mode="lines", line=dict(color=DOWN, width=1.5), hoverinfo="skip"))
    fig.update_layout(
        template="plotly_dark", height=height, margin=dict(l=0, r=0, t=2, b=2),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def render_gauge(
    value: float,
    title: str,
    subtitle: str = "",
    bands: list[tuple[float, float, str]] | None = None,
    height: int = 240,
) -> go.Figure:
    """0-100 gauge with a colored band and a needle-style threshold marker."""
    value = max(0.0, min(100.0, float(value)))
    if bands is None:  # red -> amber -> green (descriptive strength scale)
        bands = [(0, 35, "rgba(248,113,113,0.55)"),
                 (35, 65, "rgba(201,133,0,0.55)"),
                 (65, 100, "rgba(52,211,153,0.55)")]
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"font": {"size": 40, "color": "#ffffff"}},
        title={"text": f"<b>{title}</b><br><span style='font-size:12px;color:{INK_MUTED}'>{subtitle}</span>",
               "font": {"size": 15, "color": INK}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": INK_MUTED, "tickfont": {"color": INK_MUTED, "size": 10}},
            "bar": {"color": "rgba(255,255,255,0.85)", "thickness": 0.22},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [{"range": [lo, hi], "color": color} for lo, hi, color in bands],
            "threshold": {"line": {"color": "#ffffff", "width": 3}, "thickness": 0.9, "value": value},
        },
    ))
    fig.update_layout(
        template="plotly_dark", height=height, margin=dict(l=24, r=24, t=48, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif'),
    )
    return fig


def render_change_bars(
    labels: list[str],
    values: list[float],
    height: int = 320,
    suffix: str = "%",
    horizontal: bool = False,
) -> go.Figure:
    """Bars colored by sign (green/red) — the sector heatmap chart."""
    colors = [UP if v >= 0 else DOWN for v in values]
    text = [f"{v:+.2f}{suffix}" for v in values]
    if horizontal:
        fig = go.Figure(go.Bar(y=labels, x=values, orientation="h", marker_color=colors,
                               text=text, textposition="outside",
                               hovertemplate="%{y}: %{x:+.2f}" + suffix + "<extra></extra>"))
    else:
        fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors,
                               text=text, textposition="outside",
                               hovertemplate="%{x}: %{y:+.2f}" + suffix + "<extra></extra>"))
    fig.add_hline(y=0, line_color=INK_MUTED, line_width=1) if not horizontal else \
        fig.add_vline(x=0, line_color=INK_MUTED, line_width=1)
    fig.update_traces(textfont=dict(color=INK, size=11), cliponaxis=False)
    return _layout(fig, height)


def render_pie(labels: list[str], values: list[float], height: int = 340) -> go.Figure:
    """Donut allocation chart. Categorical hues in fixed order (never cycled);
    a 9th+ slice folds into the last color rather than generating a new hue."""
    colors = [CATEGORICAL[min(i, len(CATEGORICAL) - 1)] for i in range(len(labels))]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.55, sort=False,
        marker=dict(colors=colors, line=dict(color="#1a1a19", width=2)),
        textinfo="label+percent", textfont=dict(size=12),
        hovertemplate="%{label}: %{value:,.0f} (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_dark", height=height, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', color=INK),
    )
    return fig


def render_line(
    x: list,
    y: list[float],
    height: int = 300,
    suffix: str = "",
    markers: bool = False,
    color: str = SEQUENTIAL_BLUE[3],
) -> go.Figure:
    """Single-series line (macro series, yield curve). One y-axis, muted grid."""
    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="lines+markers" if markers else "lines",
        line=dict(color=color, width=2), marker=dict(size=7, color=color),
        hovertemplate="%{x}: %{y:,.2f}" + suffix + "<extra></extra>",
    ))
    if suffix:
        fig.update_yaxes(ticksuffix=suffix)
    return _layout(fig, height)


def render_weight_bars(labels: list[str], weights: list[float], height: int = 320) -> go.Figure:
    """Horizontal single-hue bars for composition weights (sequential blue)."""
    fig = go.Figure(go.Bar(
        y=labels[::-1], x=[w * 100 for w in weights[::-1]], orientation="h",
        marker_color=SEQUENTIAL_BLUE[3],
        text=[f"{w * 100:.1f}%" for w in weights[::-1]], textposition="outside",
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
    ))
    fig.update_traces(textfont=dict(color=INK, size=11), cliponaxis=False)
    fig.update_xaxes(ticksuffix="%")
    return _layout(fig, height)
