"""P-10 排程管理 — 排程清單、執行歷史、手動觸發。"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from atlas.presentation.components.theme import get_colors, metric_card


def render() -> None:
    st.title("⏰ 排程管理")
    c = get_colors()

    # ── 排程狀態 ────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(metric_card("排程服務", "🟢 運行中", status="positive"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("排程數", "6", status="neutral"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("今日執行", "4", status="neutral"), unsafe_allow_html=True)

    # ── 排程清單 ────────────────────────────────
    st.divider()
    st.subheader("排程清單")

    schedules = pd.DataFrame({
        "名稱": ["盤前 SOP", "盤中雷達啟動", "盤中雷達停止", "盤後選股", "IPO 掃描", "月度重建"],
        "Cron": ["0 8 * * 1-5", "0 9 * * 1-5", "30 13 * * 1-5",
                 "0 14 * * 1-5", "0 18 * * 5", "0 6 1 * *"],
        "工作流": ["pre_market", "intraday", "intraday_stop",
                  "post_market", "ipo_scan", "monthly_rebuild"],
        "啟用": [True, True, True, True, True, True],
        "上次執行": ["今日 08:00", "今日 09:00", "—", "—", "06-28", "07-01"],
        "狀態": ["✅ 完成", "✅ 完成", "⏳ 排程中", "⏳ 排程中", "✅ 完成", "✅ 完成"],
    })

    edited = st.data_editor(
        schedules, use_container_width=True, hide_index=True,
        column_config={
            "啟用": st.column_config.CheckboxColumn(),
        },
        disabled=["名稱", "Cron", "工作流", "上次執行", "狀態"],
    )

    # ── 手動觸發 ────────────────────────────────
    st.divider()
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        trigger_target = st.selectbox(
            "選擇工作流",
            ["pre_market", "intraday", "post_market", "ipo_scan", "monthly_rebuild"],
        )
    with col_t2:
        st.write("")  # 對齊
        st.write("")
        if st.button("▶️ 手動觸發", type="primary", use_container_width=True):
            st.success(f"已觸發工作流：{trigger_target}")

    # ── 執行歷史 ────────────────────────────────
    st.divider()
    st.subheader("執行歷史")

    history = pd.DataFrame({
        "時間": ["2025-07-02 14:00", "2025-07-02 13:30", "2025-07-02 09:00",
                 "2025-07-02 08:00", "2025-07-01 14:00", "2025-07-01 09:00"],
        "工作流": ["post_market", "intraday_stop", "intraday",
                  "pre_market", "post_market", "intraday"],
        "狀態": ["✅ 完成", "✅ 完成", "✅ 完成", "✅ 完成", "✅ 完成", "✅ 完成"],
        "耗時(秒)": [45.2, 1.5, 2.1, 18.5, 52.3, 2.0],
        "觸發方式": ["自動", "自動", "自動", "自動", "自動", "自動"],
    })
    st.dataframe(history, use_container_width=True, hide_index=True)

    # ── 新增排程 ────────────────────────────────
    st.divider()
    with st.expander("➕ 新增排程"):
        nc1, nc2, nc3 = st.columns(3)
        with nc1:
            st.text_input("排程名稱", placeholder="my_schedule")
        with nc2:
            st.text_input("Cron 表達式", placeholder="0 8 * * 1-5")
        with nc3:
            st.selectbox("工作流", ["pre_market", "intraday", "post_market",
                                   "ipo_scan", "weekly_report", "monthly_rebuild"],
                        key="new_wf")
        st.button("新增", use_container_width=True)
