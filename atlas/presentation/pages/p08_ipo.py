"""P-08 IPO 申購 — 申購列表、建議等級、蜜月期追蹤、歷史勝率。"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.components.charts import bar_chart, line_chart


def render() -> None:
    st.title("🆕 IPO 申購")
    c = get_colors()

    # ── 即將申購 ────────────────────────────────
    st.subheader("即將公開申購")

    ipo_df = pd.DataFrame({
        "代碼": ["6951", "4978", "3685"],
        "名稱": ["創新科技", "智慧電子", "綠能材料"],
        "承銷價": [85, 120, 55],
        "市場參考價": [110, 138, 62],
        "價差%": [29.4, 15.0, 12.7],
        "申購起日": ["2025-07-05", "2025-07-08", "2025-07-10"],
        "申購迄日": ["2025-07-07", "2025-07-10", "2025-07-12"],
        "建議": ["⭐⭐⭐ 推薦", "⭐⭐ 可申購", "⭐ 觀望"],
    })
    st.dataframe(ipo_df, use_container_width=True, hide_index=True,
                 column_config={
                     "價差%": st.column_config.NumberColumn(format="+%.1f%%"),
                 })

    st.info("💡 價差 > 20% 且基本面良好者建議申購。")

    # ── 蜜月期追蹤 ──────────────────────────────
    st.divider()
    st.subheader("蜜月期追蹤（上市 30 日內）")

    honeymoon_df = pd.DataFrame({
        "代碼": ["6948", "4975", "3682"],
        "名稱": ["先進半導", "數位金融", "潔淨能源"],
        "上市日": ["2025-06-15", "2025-06-08", "2025-06-01"],
        "承銷價": [100, 80, 45],
        "現價": [135, 88, 42],
        "報酬%": [35.0, 10.0, -6.7],
        "上市天數": [17, 24, 31],
        "模式": ["strong_rally", "steady_up", "decline"],
        "狀態": ["🟢 追蹤中", "🟢 追蹤中", "🔴 蜜月結束"],
    })
    st.dataframe(honeymoon_df, use_container_width=True, hide_index=True,
                 column_config={
                     "報酬%": st.column_config.NumberColumn(format="%+.1f%%"),
                 })

    # ── 歷史勝率 ────────────────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("歷史勝率統計")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(metric_card("總申購", "48", status="neutral"), unsafe_allow_html=True)
            st.markdown(metric_card("勝率(30日)", "68.7%", status="positive"), unsafe_allow_html=True)
        with c2:
            st.markdown(metric_card("平均報酬", "+15.3%", status="positive"), unsafe_allow_html=True)
            st.markdown(metric_card("最大報酬", "+85.2%", status="positive"), unsafe_allow_html=True)

    with col_b:
        st.subheader("近 12 個月 IPO 報酬")
        months = [f"2025-{m:02d}" for m in range(1, 13)]
        returns = [12.5, 8.3, -2.1, 15.7, 22.3, 18.5, 5.2, -3.8, 10.1, 25.6, 14.2, 8.9]
        fig = bar_chart(months, returns, title="月平均報酬%",
                       color_by_value=True, height=350)
        st.plotly_chart(fig, use_container_width=True)
