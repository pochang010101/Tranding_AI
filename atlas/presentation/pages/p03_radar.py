"""P-03 盤中雷達 — 即時訊號列表、偵測器統計、持倉損益、推播歷史。"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.components.charts import bar_chart


def render() -> None:
    st.title("📡 盤中雷達")
    c = get_colors()

    # ── 雷達狀態 ────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(metric_card("雷達狀態", "🟢 執行中", status="positive"), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card("今日告警", "23", status="neutral"), unsafe_allow_html=True)
    with col3:
        st.markdown(metric_card("買入訊號", "5", status="positive"), unsafe_allow_html=True)
    with col4:
        st.markdown(metric_card("賣出訊號", "2", status="negative"), unsafe_allow_html=True)

    # ── 偵測器開關 ──────────────────────────────
    st.divider()
    with st.expander("🔧 偵測器管理", expanded=False):
        detectors = [
            ("產業急拉", True), ("大單異常", True), ("爆量啟動", True),
            ("起漲觸發", True), ("均線跌破", True), ("甩轎回穩", True),
            ("出貨預警", True), ("價量背離", True), ("急拉急殺", True),
            ("流動性掃單", False), ("OB 回測", False),
        ]
        cols = st.columns(4)
        for i, (name, default) in enumerate(detectors):
            with cols[i % 4]:
                st.checkbox(name, value=default, key=f"det_{name}")

    # ── 即時訊號列表 ────────────────────────────
    st.divider()
    st.subheader("即時訊號")

    signals_df = pd.DataFrame({
        "時間": ["10:32:15", "10:28:43", "10:15:22", "09:55:10", "09:42:38",
                 "09:30:05", "09:15:22"],
        "偵測器": ["爆量啟動", "大單異常", "起漲觸發", "產業急拉", "均線跌破",
                  "爆量啟動", "大單異常"],
        "代碼": ["2454", "3008", "6547", "半導體族群", "2881", "2330", "2317"],
        "方向": ["🟢 BUY", "🟢 BUY", "🟢 BUY", "🟡 ALERT", "🔴 SELL",
                "🟢 BUY", "🟢 BUY"],
        "觸發價": [1285, 195.5, 132, None, 68.3, 890, 165],
        "嚴重度": [4, 3, 3, 4, 3, 5, 2],
        "細節": [
            "量能突破5日均量3倍", "連續大單買超", "突破前高+量增",
            "半導體族群5檔同步拉升", "跌破MA21", "開盤爆量突破",
            "法人大單進場",
        ],
    })
    st.dataframe(signals_df, use_container_width=True, hide_index=True,
                 column_config={
                     "嚴重度": st.column_config.NumberColumn(format="%d ⭐"),
                 })

    # ── 偵測器統計 ──────────────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("偵測器觸發統計")
        det_names = ["爆量啟動", "大單異常", "起漲觸發", "產業急拉", "均線跌破"]
        det_counts = [8, 5, 4, 3, 3]
        fig = bar_chart(det_names, det_counts, title="今日觸發次數",
                       horizontal=True, height=350)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("熱門標的")
        hot_codes = ["2330", "2454", "3008", "6547", "2317"]
        hot_counts = [5, 4, 3, 2, 2]
        fig = bar_chart(hot_codes, hot_counts, title="觸發次數 by 標的",
                       horizontal=True, height=350)
        st.plotly_chart(fig, use_container_width=True)

    # ── 持倉即時損益 ────────────────────────────
    st.divider()
    st.subheader("持倉即時損益")
    positions_df = pd.DataFrame({
        "代碼": ["2330", "2454", "3008"],
        "進場價": [880, 1250, 190],
        "現價": [892, 1240, 198],
        "張數": [2, 1, 3],
        "未實現損益": [24000, -10000, 24000],
        "損益%": [1.36, -0.80, 4.21],
        "R倍數": [0.8, -0.5, 1.6],
    })
    st.dataframe(positions_df, use_container_width=True, hide_index=True,
                 column_config={
                     "損益%": st.column_config.NumberColumn(format="%+.2f%%"),
                     "未實現損益": st.column_config.NumberColumn(format="$%+,d"),
                 })
