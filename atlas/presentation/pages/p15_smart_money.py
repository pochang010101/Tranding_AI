"""P-15 主力追蹤 — 主力階段偵測 + 籌碼集中度 + 多流派訊號。"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from atlas.presentation.components.charts import _apply_layout, gauge_chart
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    TW_TOP_STOCKS,
    fetch_institutional_flow,
    fetch_stock_data,
    fetch_stock_quote,
    get_pattern_signal_engine,
    get_smart_money_detector,
)

logger = logging.getLogger(__name__)

_PHASE_LABELS = {
    "accumulation": ("吸貨", "#4caf50"),
    "shakeout": ("洗盤", "#ff9800"),
    "markup": ("拉抬", "#2196f3"),
    "distribution": ("出貨", "#ef5350"),
    "unknown": ("未知", "#9e9e9e"),
}

_PHASE_DESCRIPTIONS = {
    "accumulation": "主力正在低位默默收集籌碼，盤整縮量，法人持續買超。",
    "shakeout": "短線急殺洗出浮額，但籌碼仍集中，可能是假破真洗。",
    "markup": "主力發動攻擊，放量上漲，法人積極加碼。",
    "distribution": "主力在高位出貨，爆量但價格不再創高，籌碼開始分散。",
    "unknown": "目前無明顯主力操作跡象。",
}


def render() -> None:
    st.title("🏦 主力追蹤")
    c = get_colors()

    # ── 控制列 ──
    col1, col2 = st.columns([3, 1])
    with col1:
        stock_options = [f"{code} {name}" for code, name in TW_TOP_STOCKS]
        selected = st.selectbox("選擇股票", stock_options, index=0, key="sm_stock")
        code = selected.split(" ")[0]
        name = selected.split(" ", 1)[1] if " " in selected else code
    with col2:
        period = st.selectbox("資料區間", ["3mo", "6mo", "1y"], index=1, key="sm_period")

    # ── 取得資料 ──
    df = fetch_stock_data(code, period)
    if df is None or df.empty or len(df) < 25:
        st.warning("資料不足。")
        return

    # 法人資料
    inst_data = fetch_institutional_flow(code)
    inst_net = inst_data.get("total_net", 0)

    # ── 主力階段偵測 ──
    detector = get_smart_money_detector()
    inst_series = pd.Series(np.full(len(df), float(inst_net)))
    phase_result = detector.detect(df, institutional_data=inst_series, code=code)

    # ── 多流派訊號 ──
    pattern_engine = get_pattern_signal_engine()
    pattern_result = pattern_engine.analyze(df, code=code)

    phase_label, phase_color = _PHASE_LABELS.get(
        phase_result.phase.value, ("未知", "#9e9e9e")
    )

    # ── 指標卡片 ──
    st.divider()
    cols = st.columns(5)

    quote = fetch_stock_quote(code)
    price = quote.get("price", float(df["close"].iloc[-1]))

    with cols[0]:
        st.markdown(metric_card(
            f"{name} ({code})", f"${price:,.1f}", status="neutral",
        ), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(
            f'<div style="background:{phase_color}22; border:2px solid {phase_color}; '
            f'border-radius:12px; padding:16px; text-align:center;">'
            f'<div style="font-size:14px; color:#aaa;">主力階段</div>'
            f'<div style="font-size:28px; font-weight:bold; color:{phase_color};">'
            f'{phase_label}</div>'
            f'<div style="font-size:12px; color:#888;">信心度 {phase_result.confidence:.0%}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(metric_card(
            "量比", f"{phase_result.volume_ratio:.2f}",
            status="positive" if phase_result.volume_ratio > 1.3 else "neutral",
        ), unsafe_allow_html=True)
    with cols[3]:
        streak = phase_result.institutional_streak
        st.markdown(metric_card(
            "法人連續", f"{streak:+d} 日",
            status="positive" if streak > 0 else "negative" if streak < 0 else "neutral",
        ), unsafe_allow_html=True)
    with cols[4]:
        stars = pattern_result.granville_stars
        star_display = "★" * stars + "☆" * (5 - stars)
        st.markdown(metric_card(
            "葛蘭碧", star_display, status="positive" if stars >= 3 else "neutral",
        ), unsafe_allow_html=True)

    # ── 主力階段說明 ──
    st.divider()
    desc = _PHASE_DESCRIPTIONS.get(phase_result.phase.value, "")
    st.info(f"**{phase_label}階段** — {desc}")

    if phase_result.signals:
        st.caption("偵測訊號：" + " | ".join(phase_result.signals))

    # ── 雙欄圖表 ──
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("多流派技術評分")
        fig = gauge_chart(
            pattern_result.composite_score,
            title="綜合技術分",
            height=280,
        )
        st.plotly_chart(fig, use_container_width=True)

        # 細項
        detail_rows = [
            {"指標": "葛蘭碧星評", "值": f"{stars}/5"},
            {"指標": "均線排列", "值": pattern_result.ma_alignment},
            {"指標": "均線排列分", "值": f"{pattern_result.ma_alignment_score:.1f}"},
            {"指標": "N底偵測", "值": pattern_result.n_bottom_type or "未偵測到"},
            {"指標": "綜合分數", "值": f"{pattern_result.composite_score:.1f}"},
        ]
        st.dataframe(pd.DataFrame(detail_rows), hide_index=True, use_container_width=True)

    with col_b:
        st.subheader("籌碼集中度")
        chip_val = phase_result.chip_concentration
        # 將 -1~1 轉換為 0~100 儀表
        gauge_val = (chip_val + 1) * 50
        fig2 = gauge_chart(
            gauge_val,
            title="籌碼集中度",
            height=280,
            thresholds=[
                (20, c["negative"]),
                (40, c["warning"]),
                (60, c["neutral"]),
                (80, c["positive"]),
                (100, c["accent"]),
            ],
        )
        st.plotly_chart(fig2, use_container_width=True)

        # 法人明細
        st.markdown("**三大法人淨買賣**")
        inst_rows = [
            {"法人": "外資", "淨買賣(張)": inst_data.get("foreign_net", 0)},
            {"法人": "投信", "淨買賣(張)": inst_data.get("trust_net", 0)},
            {"法人": "自營", "淨買賣(張)": inst_data.get("dealer_net", 0)},
            {"法人": "合計", "淨買賣(張)": inst_data.get("total_net", 0)},
        ]
        st.dataframe(pd.DataFrame(inst_rows), hide_index=True, use_container_width=True)

    # ── 葛蘭碧法則觸發 ──
    if pattern_result.granville_rules:
        st.divider()
        st.subheader("葛蘭碧法則觸發")
        rule_labels = {
            "B1_breakout": "B1 突破買進：均線由下轉平，價格從下方突破",
            "B2_bounce_back": "B2 回站買進：均線上揚，價格跌破後迅速站回",
            "B3_pullback_bounce": "B3 拉回買進：價格在均線上方回落未跌破即反轉",
            "B4_oversold_bounce": "B4 超跌反彈：價格暴跌遠離均線，乖離過大",
            "trend_bullish": "趨勢多頭：價格站上上揚均線",
        }
        for rule in pattern_result.granville_rules:
            label = rule_labels.get(rule, rule)
            st.success(f"✅ {label}")
