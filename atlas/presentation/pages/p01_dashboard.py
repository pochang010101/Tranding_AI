"""P-01 總覽儀表板 — 大盤環境 + 訊號摘要 + 持倉概覽 + 排程狀態。"""

from __future__ import annotations

import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card, regime_badge
from atlas.presentation.components.charts import gauge_chart, bar_chart


def render() -> None:
    st.title("📊 總覽儀表板")
    c = get_colors()
    market = st.session_state.get("market", "TW")

    # ── Row 1: 大盤環境 ────────────────────────
    st.subheader("大盤環境")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(metric_card("大盤趨勢", "多頭", status="positive"), unsafe_allow_html=True)
        st.markdown(regime_badge("BULL"), unsafe_allow_html=True)

    with col2:
        st.markdown(metric_card("市場情緒", "62", delta="GREED", status="positive"),
                    unsafe_allow_html=True)

    with col3:
        st.markdown(metric_card("市場寬度", "68%", delta="站上 MA20", status="positive"),
                    unsafe_allow_html=True)

    with col4:
        st.markdown(metric_card("漲跌比", "1.32", delta="偏多", status="positive"),
                    unsafe_allow_html=True)

    # ── Row 2: 情緒儀表 + 今日訊號 ─────────────
    st.divider()
    col_a, col_b = st.columns([1, 2])

    with col_a:
        st.subheader("情緒指數")
        fig = gauge_chart(62, title="Fear & Greed", min_val=0, max_val=100)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("今日訊號摘要")
        # Demo 資料
        demo_signals = {
            "標的": ["2330", "2454", "3008", "2881", "6547"],
            "策略": ["S1_突破", "O2_跳空", "K1_扣抵", "P2_型態", "T1_RSI"],
            "方向": ["🟢 BUY", "🟢 BUY", "🟢 BUY", "🔴 SELL", "🟢 BUY"],
            "等級": ["Lv5", "Lv4", "Lv4", "Lv2", "Lv3"],
            "觸發價": [890.0, 1285.0, 195.5, 68.3, 132.0],
        }
        st.dataframe(demo_signals, use_container_width=True, hide_index=True)

    # ── Row 3: 持倉概覽 ────────────────────────
    st.divider()
    st.subheader("持倉概覽")

    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        st.markdown(metric_card("持倉數", "5", status="neutral"), unsafe_allow_html=True)
    with col_p2:
        st.markdown(metric_card("未實現損益", "+$42,300", delta="+2.1%", status="positive"),
                    unsafe_allow_html=True)
    with col_p3:
        st.markdown(metric_card("今日損益", "+$8,500", delta="+0.4%", status="positive"),
                    unsafe_allow_html=True)
    with col_p4:
        st.markdown(metric_card("勝率", "65.2%", delta="avg R=1.8", status="positive"),
                    unsafe_allow_html=True)

    # ── Row 4: 四主軸分佈 ──────────────────────
    st.divider()
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.subheader("候選清單 — 四主軸分數")
        fig = bar_chart(
            labels=["2330", "2454", "3008", "6547", "2881"],
            values=[82.5, 76.3, 71.8, 68.5, 55.2],
            title="Top 5 主軸總分",
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_c2:
        st.subheader("排程狀態")
        schedules = {
            "工作流": ["盤前 SOP", "盤中雷達", "盤後選股", "月度重建"],
            "狀態": ["✅ 完成", "🔄 執行中", "⏳ 排程中", "✅ 完成"],
            "上次執行": ["08:30", "進行中", "—", "07-01"],
            "下次執行": ["明日 08:00", "—", "今日 14:00", "08-01"],
        }
        st.dataframe(schedules, use_container_width=True, hide_index=True)

    # Footer
    st.divider()
    st.caption(f"市場：{market} | 資料更新時間：即時 | Atlas v5.0")
