"""P-06 持倉追蹤 — 持倉列表、進出場紀錄、績效統計。"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.components.charts import equity_curve, histogram, bar_chart


def render() -> None:
    st.title("💼 持倉追蹤")
    c = get_colors()

    # ── 績效總覽 ────────────────────────────────
    st.subheader("績效總覽")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(metric_card("帳戶淨值", "$1,142,300", status="positive"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("總報酬", "+14.2%", status="positive"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("勝率", "62.5%", status="positive"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("平均 R", "1.65", status="positive"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card("期望值", "$2,850", status="positive"), unsafe_allow_html=True)

    # ── 未平倉持倉 ──────────────────────────────
    st.divider()
    st.subheader("未平倉持倉")

    positions = pd.DataFrame({
        "代碼": ["2330", "2454", "3008", "6547", "2881"],
        "名稱": ["台積電", "聯發科", "大立光", "高端疫苗", "富邦金"],
        "進場日": ["2025-06-15", "2025-06-18", "2025-06-20", "2025-06-22", "2025-06-25"],
        "進場價": [880, 1250, 190, 125, 67],
        "現價": [895, 1240, 205, 132, 65.5],
        "張數": [2, 1, 3, 5, 10],
        "停損": [855, 1200, 178, 115, 63],
        "目標": [950, 1350, 230, 155, 75],
        "未實現損益": [30000, -10000, 45000, 35000, -15000],
        "損益%": [1.70, -0.80, 7.89, 5.60, -2.24],
        "R倍數": [0.60, -0.20, 1.25, 0.70, -0.38],
    })

    st.dataframe(positions, use_container_width=True, hide_index=True,
                 column_config={
                     "損益%": st.column_config.NumberColumn(format="%+.2f%%"),
                     "未實現損益": st.column_config.NumberColumn(format="$%+,d"),
                     "R倍數": st.column_config.NumberColumn(format="%+.2f"),
                 })

    # ── 建倉 / 平倉 ────────────────────────────
    st.divider()
    tab_add, tab_close, tab_calc = st.tabs(["➕ 建倉", "❌ 平倉", "🔢 倉位計算"])

    with tab_add:
        ac1, ac2, ac3, ac4 = st.columns(4)
        with ac1:
            st.text_input("代碼", key="add_code", placeholder="2330")
        with ac2:
            st.number_input("進場價", key="add_price", value=0.0, step=0.5)
        with ac3:
            st.number_input("停損價", key="add_stop", value=0.0, step=0.5)
        with ac4:
            st.number_input("張數", key="add_lots", value=1, step=1)
        st.button("確認建倉", type="primary", use_container_width=True)

    with tab_close:
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            st.selectbox("選擇持倉", ["2330 台積電", "2454 聯發科", "3008 大立光"])
        with cc2:
            st.number_input("出場價", key="close_price", value=0.0, step=0.5)
        with cc3:
            st.text_input("出場原因", key="close_reason", placeholder="停損/停利/訊號")
        st.button("確認平倉", type="primary", use_container_width=True)

    with tab_calc:
        st.subheader("ATR 動態倉位計算")
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            entry = st.number_input("預計進場價", value=100.0, step=0.5)
        with pc2:
            stop = st.number_input("停損價", value=95.0, step=0.5)
        with pc3:
            risk_pct = st.slider("風險百分比 %", 0.5, 5.0, 2.0, 0.5)

        if entry > 0 and stop > 0 and entry != stop:
            equity = 1_000_000
            risk_amount = equity * risk_pct / 100
            risk_per_share = abs(entry - stop)
            lots = max(1, int(risk_amount / risk_per_share / 1000))
            st.success(f"建議買入 **{lots} 張**（{lots * 1000} 股），風險金額 ${lots * 1000 * risk_per_share:,.0f}")

    # ── 歷史績效 ────────────────────────────────
    st.divider()
    st.subheader("歷史績效曲線")
    rng = np.random.default_rng(42)
    eq = [1_000_000]
    for _ in range(100):
        eq.append(eq[-1] * (1 + rng.normal(0.002, 0.015)))
    fig = equity_curve(eq, height=400)
    st.plotly_chart(fig, use_container_width=True)

    # ── R 倍數分佈 ──────────────────────────────
    st.divider()
    st.subheader("R 倍數分佈")
    r_vals = list(rng.normal(0.5, 1.2, 50))
    fig = histogram(r_vals, title="已平倉 R 倍數", x_label="R", bins=20, height=350)
    st.plotly_chart(fig, use_container_width=True)
