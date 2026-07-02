"""P-02 盤前分析 — 美股收盤、台指期夜盤、情緒、缺口預測。"""

from __future__ import annotations

import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card, regime_badge
from atlas.presentation.components.charts import bar_chart, gauge_chart


def render() -> None:
    st.title("🌏 盤前分析")
    c = get_colors()

    # ── 美股四大指數 ────────────────────────────
    st.subheader("美股四大指數（昨日收盤）")
    c1, c2, c3, c4 = st.columns(4)
    indices = [
        ("道瓊 DJI", "42,850", "+0.35%", "positive"),
        ("S&P 500", "5,920", "+0.52%", "positive"),
        ("NASDAQ", "19,250", "+0.78%", "positive"),
        ("費半 SOX", "5,180", "+1.25%", "positive"),
    ]
    for col, (name, val, delta, status) in zip([c1, c2, c3, c4], indices):
        with col:
            st.markdown(metric_card(name, val, delta, status), unsafe_allow_html=True)

    # ── 代表性美股 ──────────────────────────────
    st.divider()
    st.subheader("8 檔代表性美股")
    stocks = {
        "代碼": ["AAPL", "NVDA", "TSM", "MSFT", "GOOGL", "AMZN", "META", "AVGO"],
        "名稱": ["Apple", "NVIDIA", "台積電ADR", "Microsoft", "Google", "Amazon", "Meta", "Broadcom"],
        "收盤價": [195.2, 135.8, 178.5, 430.1, 175.3, 195.7, 510.2, 175.6],
        "漲跌%": [+0.8, +2.1, +1.5, +0.3, +0.5, +0.7, +1.2, +1.8],
    }
    st.dataframe(stocks, use_container_width=True, hide_index=True,
                 column_config={"漲跌%": st.column_config.NumberColumn(format="%+.1f%%")})

    # ── 台指期夜盤 + 缺口預測 ──────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("台指期夜盤")
        st.markdown(metric_card("台指期", "22,350", "+85 (+0.38%)", "positive"),
                    unsafe_allow_html=True)
        st.markdown(metric_card("小台期", "22,345", "+83 (+0.37%)", "positive"),
                    unsafe_allow_html=True)

    with col_b:
        st.subheader("缺口預測")
        st.markdown(metric_card("預測方向", "⬆️ 跳空上漲", status="positive"),
                    unsafe_allow_html=True)
        st.markdown(metric_card("預測幅度", "+0.45%", delta="信心度 72%", status="positive"),
                    unsafe_allow_html=True)

        factors = ["台指期夜盤", "費半指數", "S&P500", "ADR溢價"]
        weights = [0.38, 0.25, 0.20, 0.15]
        fig = bar_chart(factors, [w * 100 for w in weights],
                       title="缺口預測因子權重 %", height=300)
        st.plotly_chart(fig, use_container_width=True)

    # ── 大盤環境 + 情緒 ────────────────────────
    st.divider()
    col_r1, col_r2 = st.columns(2)

    with col_r1:
        st.subheader("大盤環境")
        st.markdown(regime_badge("BULL"), unsafe_allow_html=True)
        st.markdown(metric_card("趨勢強度", "2.8", delta="均線多頭排列", status="positive"),
                    unsafe_allow_html=True)

    with col_r2:
        st.subheader("市場情緒")
        fig = gauge_chart(62, title="情緒指數", height=250)
        st.plotly_chart(fig, use_container_width=True)

    # ── 盤前摘要 ────────────────────────────────
    st.divider()
    st.subheader("📋 盤前摘要")
    st.info("""
    **今日研判**：美股三大指數收紅，費半領漲 +1.25%。台指期夜盤上漲 85 點。
    預測台股開盤小幅跳空上漲約 0.45%。大盤維持多頭格局，情緒偏貪婪。
    建議關注半導體族群輪動。
    """)
