"""P-07 回測分析 — 策略選擇、參數設定、回測結果、參數掃描、蒙地卡羅。"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.components.charts import equity_curve, histogram, bar_chart, line_chart


def render() -> None:
    st.title("📈 回測分析")
    c = get_colors()

    # ── 控制面板 ────────────────────────────────
    with st.expander("⚙️ 回測設定", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            strategy = st.selectbox("策略", [
                "S1_均線突破", "S2_量價齊揚", "O1_跳空", "K1_扣抵翻揚",
                "P1_W底", "T1_RSI反轉", "SD1_空頭反轉",
            ])
        with col2:
            date_range = st.date_input("回測期間", value=[], key="bt_dates")
        with col3:
            capital = st.number_input("初始資金", value=1_000_000, step=100_000, format="%d")

        col4, col5, col6 = st.columns(3)
        with col4:
            include_cost = st.checkbox("含交易成本", value=True)
        with col5:
            market = st.session_state.get("market", "TW")
            st.text(f"市場：{market}")
        with col6:
            if st.button("🚀 執行回測", type="primary", use_container_width=True):
                st.session_state["bt_running"] = True

    # ── 回測結果摘要 ────────────────────────────
    st.divider()
    st.subheader("回測結果")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(metric_card("總報酬", "+28.5%", status="positive"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("年化報酬", "+18.2%", status="positive"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("Sharpe", "1.35", status="positive"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("最大回撤", "-12.3%", status="negative"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card("勝率", "58.3%", status="positive"), unsafe_allow_html=True)
    with c6:
        st.markdown(metric_card("獲利因子", "1.82", status="positive"), unsafe_allow_html=True)

    # ── 淨值曲線 ────────────────────────────────
    st.divider()
    rng = np.random.default_rng(42)
    returns = rng.normal(0.001, 0.015, 250)
    equity = [capital]
    for r in returns:
        equity.append(equity[-1] * (1 + r))

    fig = equity_curve(equity, title="淨值曲線 + 回撤", height=500)
    st.plotly_chart(fig, use_container_width=True)

    # ── 交易明細 + R 倍數 ──────────────────────
    st.divider()
    tab1, tab2, tab3 = st.tabs(["📋 交易明細", "📊 R 倍數分佈", "🎲 蒙地卡羅"])

    with tab1:
        trades_df = pd.DataFrame({
            "代碼": ["2330", "2454", "3008", "2881", "6547", "2317", "2382", "3711"],
            "進場日": ["2025-01-05", "2025-01-12", "2025-01-18", "2025-02-01",
                      "2025-02-10", "2025-02-20", "2025-03-01", "2025-03-10"],
            "出場日": ["2025-01-20", "2025-01-28", "2025-02-05", "2025-02-15",
                      "2025-02-25", "2025-03-05", "2025-03-15", "2025-03-22"],
            "進場價": [880, 1250, 190, 67, 125, 165, 280, 820],
            "出場價": [920, 1190, 210, 65, 140, 170, 265, 870],
            "損益%": [4.5, -4.8, 10.5, -3.0, 12.0, 3.0, -5.4, 6.1],
            "R倍數": [1.8, -1.2, 3.5, -1.0, 4.0, 1.0, -1.8, 2.0],
            "持有天數": [15, 16, 18, 14, 15, 13, 14, 12],
        })
        st.dataframe(trades_df, use_container_width=True, hide_index=True,
                     column_config={
                         "損益%": st.column_config.NumberColumn(format="%.1f%%"),
                         "R倍數": st.column_config.NumberColumn(format="%.1f"),
                     })

    with tab2:
        r_values = list(rng.normal(0.5, 1.5, 100))
        fig = histogram(r_values, title="R 倍數分佈", x_label="R 倍數", bins=25, height=400)
        st.plotly_chart(fig, use_container_width=True)

        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            st.metric("平均 R", f"{np.mean(r_values):.2f}")
        with col_r2:
            st.metric("中位數 R", f"{np.median(r_values):.2f}")
        with col_r3:
            st.metric("期望值", f"{np.mean(r_values) * 0.58:.2f}")

    with tab3:
        st.subheader("蒙地卡羅模擬")
        mc_col1, mc_col2 = st.columns([1, 2])

        with mc_col1:
            mc_paths = st.slider("模擬路徑數", 100, 5000, 1000, 100)
            mc_wr = st.slider("勝率 %", 30, 80, 58)
            mc_payoff = st.slider("損益比", 0.5, 5.0, 1.8, 0.1)
            st.button("▶️ 執行模擬", use_container_width=True)

        with mc_col2:
            # Demo: 蒙地卡羅分佈
            final_values = list(rng.lognormal(14.0, 0.3, 1000))
            fig = histogram(final_values, title="最終資金分佈", x_label="最終資金", bins=40, height=400)
            st.plotly_chart(fig, use_container_width=True)

        # MC 統計
        arr = np.array(final_values)
        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.metric("P5（悲觀）", f"${np.percentile(arr, 5):,.0f}")
        with mc2:
            st.metric("P50（中位）", f"${np.percentile(arr, 50):,.0f}")
        with mc3:
            st.metric("P95（樂觀）", f"${np.percentile(arr, 95):,.0f}")
        with mc4:
            ruin = np.mean(arr < capital * 0.5) * 100
            st.metric("破產機率", f"{ruin:.1f}%")

    # ── 參數掃描 ────────────────────────────────
    st.divider()
    st.subheader("參數網格掃描")
    with st.expander("設定參數範圍"):
        ps_col1, ps_col2 = st.columns(2)
        with ps_col1:
            st.text_input("MA 快線", value="5, 8, 13")
        with ps_col2:
            st.text_input("MA 慢線", value="21, 34, 55")
        st.button("🔍 開始掃描", use_container_width=True)
