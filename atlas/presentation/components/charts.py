"""Plotly 圖表工廠 — K線、折線、直方圖、熱力圖、儀表。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from atlas.presentation.components.theme import get_colors


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert #RRGGBB to rgba() string (Plotly doesn't support 8-digit hex)."""
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _apply_layout(fig: go.Figure, title: str = "", height: int = 500) -> go.Figure:
    """統一圖表佈局。"""
    c = get_colors()
    fig.update_layout(
        title=title,
        template=c["plotly_template"],
        plot_bgcolor=c["plotly_bg"],
        paper_bgcolor=c["plotly_paper"],
        font=dict(color=c["text_primary"]),
        height=height,
        margin=dict(l=50, r=30, t=50, b=40),
        xaxis=dict(gridcolor=c["plotly_grid"]),
        yaxis=dict(gridcolor=c["plotly_grid"]),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


# ── K 線圖 ──────────────────────────────────────

def candlestick_chart(
    df: pd.DataFrame,
    ma_periods: list[int] | None = None,
    volume: bool = True,
    signals: list[dict[str, Any]] | None = None,
    title: str = "",
    height: int = 700,
) -> go.Figure:
    """互動式 K 線圖 + 均線 + 成交量 + 訊號標記。

    Args:
        df: 含 date/open/high/low/close/volume 的 DataFrame
        ma_periods: 均線週期列表（如 [8, 21, 55]）
        volume: 是否顯示成交量
        signals: [{"date": ..., "type": "BUY"|"SELL", "price": ...}]
    """
    c = get_colors()
    rows = 2 if volume else 1
    row_heights = [0.7, 0.3] if volume else [1.0]
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.03, row_heights=row_heights,
    )

    # K 線
    fig.add_trace(go.Candlestick(
        x=df["date"] if "date" in df.columns else df.index,
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=c["candle_up"],
        decreasing_line_color=c["candle_down"],
        increasing_fillcolor=c["candle_up"],
        decreasing_fillcolor=c["candle_down"],
        name="K線",
    ), row=1, col=1)

    # 均線
    ma_colors = ["#ff9800", "#2196f3", "#e91e63", "#9c27b0"]
    for i, period in enumerate(ma_periods or []):
        col_name = f"MA{period}"
        if col_name in df.columns:
            fig.add_trace(go.Scatter(
                x=df["date"] if "date" in df.columns else df.index,
                y=df[col_name],
                name=col_name,
                line=dict(width=1.2, color=ma_colors[i % len(ma_colors)]),
            ), row=1, col=1)

    # 訊號標記
    if signals:
        for sig in signals:
            color = c["positive"] if sig.get("type") == "BUY" else c["negative"]
            symbol = "triangle-up" if sig.get("type") == "BUY" else "triangle-down"
            fig.add_trace(go.Scatter(
                x=[sig["date"]],
                y=[sig["price"]],
                mode="markers",
                marker=dict(size=12, color=color, symbol=symbol),
                name=sig.get("type", ""),
                showlegend=False,
            ), row=1, col=1)

    # 成交量
    if volume and "volume" in df.columns:
        colors = [
            c["candle_up"] if row["close"] >= row["open"] else c["candle_down"]
            for _, row in df.iterrows()
        ]
        fig.add_trace(go.Bar(
            x=df["date"] if "date" in df.columns else df.index,
            y=df["volume"],
            marker_color=colors,
            name="成交量",
            opacity=0.6,
        ), row=2, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False)
    return _apply_layout(fig, title, height)


# ── 折線圖 ──────────────────────────────────────

def line_chart(
    df: pd.DataFrame,
    x: str,
    y_columns: list[str],
    title: str = "",
    height: int = 400,
    fill: bool = False,
) -> go.Figure:
    """多條折線圖。"""
    fig = go.Figure()
    colors = ["#00d4aa", "#667eea", "#ff9800", "#e91e63", "#9c27b0"]
    for i, col in enumerate(y_columns):
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df[x], y=df[col], name=col,
                line=dict(color=colors[i % len(colors)]),
                fill="tozeroy" if fill and i == 0 else None,
            ))
    return _apply_layout(fig, title, height)


# ── 直方圖 ──────────────────────────────────────

def histogram(
    values: list[float],
    title: str = "",
    x_label: str = "",
    bins: int = 30,
    height: int = 400,
) -> go.Figure:
    """直方圖（R倍數分佈、蒙地卡羅分佈）。"""
    c = get_colors()
    fig = go.Figure(go.Histogram(
        x=values, nbinsx=bins,
        marker_color=c["accent"], opacity=0.8,
    ))
    fig.update_layout(xaxis_title=x_label)
    return _apply_layout(fig, title, height)


# ── 熱力圖 ──────────────────────────────────────

def heatmap(
    df: pd.DataFrame,
    x: str, y: str, z: str,
    title: str = "",
    height: int = 500,
    colorscale: str = "RdYlGn",
) -> go.Figure:
    """熱力圖（產業 RS、參數掃描）。"""
    pivot = df.pivot_table(index=y, columns=x, values=z, aggfunc="first")
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=colorscale,
        texttemplate="%{z:.1f}",
    ))
    return _apply_layout(fig, title, height)


# ── 儀表盤（Gauge）────────────────────────────

def gauge_chart(
    value: float,
    title: str = "",
    min_val: float = 0,
    max_val: float = 100,
    thresholds: list[tuple[float, str]] | None = None,
    height: int = 250,
) -> go.Figure:
    """儀表圖（情緒指數、強度指標）。"""
    c = get_colors()
    steps = thresholds or [
        (20, c["negative"]),
        (40, c["warning"]),
        (60, c["neutral"]),
        (80, c["positive"]),
        (100, c["accent"]),
    ]
    gauge_steps = []
    prev = min_val
    for threshold, color in steps:
        gauge_steps.append(dict(range=[prev, threshold], color=_hex_to_rgba(color, 0.2)))
        prev = threshold

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title=dict(text=title, font=dict(color=c["text_primary"])),
        gauge=dict(
            axis=dict(range=[min_val, max_val], tickcolor=c["text_secondary"]),
            bar=dict(color=c["accent"]),
            steps=gauge_steps,
            bordercolor=c["border"],
        ),
        number=dict(font=dict(color=c["text_primary"])),
    ))
    return _apply_layout(fig, height=height)


# ── 柱狀圖 ──────────────────────────────────────

def bar_chart(
    labels: list[str],
    values: list[float],
    title: str = "",
    horizontal: bool = False,
    color_by_value: bool = False,
    height: int = 400,
) -> go.Figure:
    """柱狀圖。"""
    c = get_colors()
    if color_by_value:
        colors = [c["positive"] if v >= 0 else c["negative"] for v in values]
    else:
        colors = c["accent"]

    if horizontal:
        fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", marker_color=colors))
    else:
        fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors))
    return _apply_layout(fig, title, height)


# ── 淨值曲線 ────────────────────────────────────

def equity_curve(
    equity: list[float],
    title: str = "淨值曲線",
    height: int = 400,
) -> go.Figure:
    """淨值曲線 + 回撤區域。"""
    c = get_colors()
    import numpy as np
    eq = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak * 100

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05, row_heights=[0.7, 0.3])

    fig.add_trace(go.Scatter(
        y=eq, mode="lines", name="淨值",
        line=dict(color=c["accent"], width=2),
        fill="tozeroy", fillcolor=_hex_to_rgba(c["accent"], 0.08),
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        y=-dd, mode="lines", name="回撤%",
        line=dict(color=c["negative"], width=1),
        fill="tozeroy", fillcolor=_hex_to_rgba(c["negative"], 0.13),
    ), row=2, col=1)

    return _apply_layout(fig, title, height)
