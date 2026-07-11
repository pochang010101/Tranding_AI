"""P-14 交易價位 — 支撐壓力 + Fibonacci 回撤 + 買點建議。"""

from __future__ import annotations

import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from atlas.presentation.components.charts import _apply_layout
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    TW_TOP_STOCKS,
    fetch_stock_data,
    fetch_stock_quote,
    get_indicator_lib,
    get_price_level_calc,
)

logger = logging.getLogger(__name__)


def _price_level_chart(
    df: pd.DataFrame, result, title: str = "", height: int = 600,
) -> go.Figure:
    """K 線圖 + 支撐壓力線 + Fibonacci 區間 + 買點標記。"""
    c = get_colors()
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.03, row_heights=[0.75, 0.25],
    )

    x_axis = df.index

    # K 線
    fig.add_trace(go.Candlestick(
        x=x_axis,
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=c["candle_up"],
        decreasing_line_color=c["candle_down"],
        increasing_fillcolor=c["candle_up"],
        decreasing_fillcolor=c["candle_down"],
        name="K線",
    ), row=1, col=1)

    # 支撐線（綠色虛線）
    for i, s in enumerate(result.supports[:3]):
        fig.add_hline(
            y=s, line_dash="dash", line_color="#4caf50", line_width=1,
            annotation_text=f"S{i+1}: {s:.1f}",
            annotation_position="left",
            row=1, col=1,
        )

    # 壓力線（紅色虛線）
    for i, r in enumerate(result.resistances[:3]):
        fig.add_hline(
            y=r, line_dash="dash", line_color="#ef5350", line_width=1,
            annotation_text=f"R{i+1}: {r:.1f}",
            annotation_position="left",
            row=1, col=1,
        )

    # Fibonacci 區間（半透明色帶）
    fibo_colors = ["rgba(255,152,0,0.08)", "rgba(33,150,243,0.08)",
                   "rgba(156,39,176,0.08)", "rgba(0,188,212,0.08)",
                   "rgba(233,30,99,0.08)"]
    for i, (label, level) in enumerate(result.fibonacci.items()):
        fig.add_hline(
            y=level, line_dash="dot", line_color="#888", line_width=0.8,
            annotation_text=f"Fib {label}: {level:.1f}",
            annotation_position="right",
            row=1, col=1,
        )

    # 買點標記
    last_x = x_axis[-1]
    if result.pullback_buy:
        fig.add_trace(go.Scatter(
            x=[last_x], y=[result.pullback_buy],
            mode="markers+text",
            marker=dict(size=12, color="#4caf50", symbol="triangle-up"),
            text=[f"拉回買 {result.pullback_buy:.1f}"],
            textposition="top center",
            name="拉回買點",
        ), row=1, col=1)

    if result.breakout_buy:
        fig.add_trace(go.Scatter(
            x=[last_x], y=[result.breakout_buy],
            mode="markers+text",
            marker=dict(size=12, color="#2196f3", symbol="diamond"),
            text=[f"突破買 {result.breakout_buy:.1f}"],
            textposition="top center",
            name="突破買點",
        ), row=1, col=1)

    if result.stop_loss:
        fig.add_hline(
            y=result.stop_loss, line_dash="dashdot", line_color="#ff1744", line_width=1.5,
            annotation_text=f"停損: {result.stop_loss:.1f}",
            annotation_position="left",
            row=1, col=1,
        )

    # 成交量
    if "volume" in df.columns:
        vol_colors = [
            c["candle_up"] if row["close"] >= row["open"] else c["candle_down"]
            for _, row in df.iterrows()
        ]
        fig.add_trace(go.Bar(
            x=x_axis, y=df["volume"],
            marker_color=vol_colors, name="成交量", opacity=0.6,
        ), row=2, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False)
    return _apply_layout(fig, title, height)


def render() -> None:
    st.title("📐 交易價位分析")
    c = get_colors()

    # ── 控制列 ──
    col1, col2 = st.columns([3, 1])
    with col1:
        stock_options = [f"{code} {name}" for code, name in TW_TOP_STOCKS]
        selected = st.selectbox("選擇股票", stock_options, index=0)
        code = selected.split(" ")[0]
        name = selected.split(" ", 1)[1] if " " in selected else code
    with col2:
        period = st.selectbox("資料區間", ["3mo", "6mo", "1y"], index=1)

    # ── 取得資料 ──
    df = fetch_stock_data(code, period)
    if df is None or df.empty or len(df) < 20:
        st.warning("資料不足，請換股或延長區間。")
        return

    calc = get_price_level_calc()
    result = calc.calculate(df, code=code)

    # ── 指標卡片 ──
    st.divider()
    cols = st.columns(6)

    quote = fetch_stock_quote(code)
    price = quote.get("price", result.current_price)
    prev = quote.get("prev_close", 0)
    chg_pct = ((price - prev) / prev * 100) if prev > 0 else 0.0

    with cols[0]:
        st.markdown(metric_card(
            f"{name} ({code})", f"${price:,.1f}",
            delta=f"{chg_pct:+.2f}%",
            status="positive" if chg_pct >= 0 else "negative",
        ), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(metric_card(
            "ATR", f"{result.atr:.2f}" if result.atr else "—", status="neutral",
        ), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(metric_card(
            "拉回買點", f"${result.pullback_buy:,.1f}" if result.pullback_buy else "—",
            status="positive",
        ), unsafe_allow_html=True)
    with cols[3]:
        st.markdown(metric_card(
            "突破買點", f"${result.breakout_buy:,.1f}" if result.breakout_buy else "—",
            status="positive",
        ), unsafe_allow_html=True)
    with cols[4]:
        st.markdown(metric_card(
            "停損", f"${result.stop_loss:,.1f}" if result.stop_loss else "—",
            status="negative",
        ), unsafe_allow_html=True)
    with cols[5]:
        rr = result.risk_reward_ratio
        st.markdown(metric_card(
            "風報比", f"{rr:.2f}" if rr else "—",
            status="positive" if rr and rr >= 2 else "warning" if rr else "neutral",
        ), unsafe_allow_html=True)

    # ── K 線圖 + 價位 ──
    st.divider()
    fig = _price_level_chart(df, result, title=f"{name} ({code}) — 支撐壓力 + Fibonacci")
    st.plotly_chart(fig, use_container_width=True)

    # ── 明細表 ──
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("支撐 / 壓力價位")
        rows = []
        for i, s in enumerate(result.supports):
            rows.append({"類型": "支撐", "序號": f"S{i+1}", "價位": round(s, 2)})
        for i, r in enumerate(result.resistances):
            rows.append({"類型": "壓力", "序號": f"R{i+1}", "價位": round(r, 2)})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("無明顯支撐壓力（資料太短或趨勢太強）")

    with col_b:
        st.subheader("Fibonacci 回撤")
        if result.fibonacci:
            fibo_rows = [{"比例": k, "價位": v} for k, v in result.fibonacci.items()]
            st.dataframe(pd.DataFrame(fibo_rows), hide_index=True, use_container_width=True)
        else:
            st.info("無 Fibonacci 資料")
