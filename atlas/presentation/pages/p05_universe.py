"""P-05 選股池管理 — 四層篩選結果、手動調整、歷史變更。"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.components.charts import bar_chart


def render() -> None:
    st.title("🗂️ 選股池管理")
    c = get_colors()

    # ── 當前池狀態 ──────────────────────────────
    st.subheader("當前選股池")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card("全市場", "1,856", status="neutral"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("L1 流動性", "823", delta="通過率 44%", status="neutral"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("L2+L3 篩選", "312", delta="通過率 38%", status="neutral"),
                    unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("最終池", "285", delta="通過率 15%", status="positive"),
                    unsafe_allow_html=True)

    # ── 四層篩選漏斗 ────────────────────────────
    st.divider()
    layers = ["全市場", "L1 流動性", "L2 技術面", "L3 策略適性", "L4 排除"]
    passed = [1856, 823, 450, 312, 285]
    fig = bar_chart(layers, passed, title="四層篩選漏斗", height=350)
    st.plotly_chart(fig, use_container_width=True)

    # ── 篩選條件 ────────────────────────────────
    st.divider()
    with st.expander("📋 篩選條件明細"):
        st.markdown("""
        | 層級 | 條件 | 說明 |
        |------|------|------|
        | L1 流動性 | 日均量 > 500張, 股價 > 10元 | 排除低流動性 |
        | L2 技術面 | 收盤 > MA55 | 中期趨勢向上 |
        | L3 策略適性 | ATR > 0.5% | 足夠波動度 |
        | L4 排除 | 非暫停/下市/警示 | 排除問題股 |
        """)

    # ── 產業分佈 ────────────────────────────────
    st.divider()
    st.subheader("池中產業分佈")
    ind_names = ["半導體", "金融", "電子零組件", "光電", "傳產", "生技", "航運", "其他"]
    ind_counts = [52, 38, 35, 28, 42, 25, 18, 47]
    fig = bar_chart(ind_names, ind_counts, title="產業股數分佈", horizontal=True, height=400)
    st.plotly_chart(fig, use_container_width=True)

    # ── 手動調整 ────────────────────────────────
    st.divider()
    st.subheader("手動調整")
    col_add, col_rm = st.columns(2)
    with col_add:
        add_codes = st.text_input("手動加入（逗號分隔）", placeholder="2330, 2454")
        st.button("➕ 加入", use_container_width=True)
    with col_rm:
        rm_codes = st.text_input("手動排除（逗號分隔）", placeholder="1234, 5678")
        st.button("➖ 排除", use_container_width=True)

    # ── 月度差異 ────────────────────────────────
    st.divider()
    st.subheader("月度重建差異")
    diff_df = pd.DataFrame({
        "類型": ["新增", "新增", "新增", "移除", "移除"],
        "代碼": ["6891", "3443", "2618", "1590", "2105"],
        "名稱": ["長聖", "創意", "長榮航", "亞德客-KY", "正新"],
        "原因": ["流動性達標", "技術面轉多", "策略適性通過", "跌破MA55", "量能萎縮"],
    })
    st.dataframe(diff_df, use_container_width=True, hide_index=True)

    # ── 重建按鈕 ────────────────────────────────
    st.divider()
    if st.button("🔄 強制重建選股池", type="primary"):
        st.info("重建中... 預計需要 2-3 分鐘。")
