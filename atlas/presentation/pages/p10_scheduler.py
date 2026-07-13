"""P-10 排程管理 — 排程清單、手動觸發、執行歷史。"""

from __future__ import annotations

import asyncio

import pandas as pd
import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import get_scheduler, get_workflow_engine


def render() -> None:
    st.title("⏰ 排程管理")
    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
<b>排程狀態</b>：🟢 正常執行、🟡 等待中、🔴 執行失敗｜
<b>執行時間</b>：各任務 cron 排程時間（台灣時區 UTC+8）｜
<b>下次執行</b>：預計下一次觸發時間｜
<b>任務類型</b>：pre_market(盤前 08:00)、intraday(盤中 09:00)、post_market(盤後 13:45)、monthly(月度重建 週日 20:00)｜
<b>非交易日</b>：週末/假日自動跳過（monthly_rebuild 除外）
</div>
""", unsafe_allow_html=True)
    get_colors()

    scheduler = get_scheduler()
    wf_engine = get_workflow_engine()

    # 確保預設排程已載入
    schedules = asyncio.run(scheduler.list_schedules()) if not hasattr(st.session_state, '_sched_init') else []
    try:
        schedules = asyncio.run(scheduler.list_schedules())
    except Exception:
        schedules = []

    # ── 排程狀態 ────────────────────────────────
    active = sum(1 for s in schedules if s.get("enabled"))
    c1, c2, c3 = st.columns(3)
    with c1:
        running = "🟢 運行中" if scheduler._running else "⏸️ 已停止"
        st.markdown(metric_card("排程服務", running,
                    status="positive" if scheduler._running else "neutral"),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("排程數", str(len(schedules)), status="neutral"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("啟用中", str(active), status="neutral"),
                    unsafe_allow_html=True)

    # ── 排程清單 ────────────────────────────────
    st.divider()
    st.subheader("排程清單")

    if schedules:
        sched_df = pd.DataFrame(schedules)
        sched_df = sched_df.rename(columns={
            "name": "名稱", "cron_expr": "Cron",
            "workflow_name": "工作流", "enabled": "啟用",
            "last_run": "上次執行",
        })
        st.data_editor(
            sched_df, width="stretch", hide_index=True,
            column_config={"啟用": st.column_config.CheckboxColumn()},
            disabled=["名稱", "Cron", "工作流", "上次執行"],
        )
    else:
        st.info("尚無排程。啟動排程服務後將自動載入預設排程。")

    # ── 手動觸發 ────────────────────────────────
    st.divider()
    st.subheader("手動觸發工作流")

    workflow_options = [
        "pre_market", "intraday", "post_market",
        "ipo_scan", "weekly_report", "monthly_rebuild",
    ]
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        trigger_target = st.selectbox("選擇工作流", workflow_options)
    with col_t2:
        st.write("")
        st.write("")
        if st.button("▶️ 手動觸發", type="primary", width="stretch"):
            with st.spinner(f"執行 {trigger_target}..."):
                try:
                    result = asyncio.run(wf_engine.run(trigger_target))
                    st.success(f"工作流 `{trigger_target}` 執行完成")
                    st.json(result)
                except Exception as exc:
                    st.error(f"執行失敗：{exc}")

    # ── 執行歷史 ────────────────────────────────
    st.divider()
    st.subheader("執行歷史")

    try:
        history = asyncio.run(wf_engine.get_execution_history())
    except Exception:
        history = []

    if history:
        hist_df = pd.DataFrame(history)
        st.dataframe(hist_df, width="stretch", hide_index=True)
    else:
        st.info("尚無執行紀錄。觸發工作流後會顯示歷史。")

    # ── 工作流狀態 ────────────────────────────────
    st.divider()
    st.subheader("各工作流狀態")

    status_data = {"工作流": [], "狀態": [], "上次執行": []}
    for wf_name in workflow_options:
        try:
            status = asyncio.run(wf_engine.get_status(wf_name))
        except Exception:
            status = {"status": "unknown"}
        icon = {"completed": "✅", "running": "🔄", "failed": "❌",
                "never_run": "⏳"}.get(status.get("status", ""), "❓")
        status_data["工作流"].append(wf_name)
        status_data["狀態"].append(f"{icon} {status.get('status', 'unknown')}")
        status_data["上次執行"].append(status.get("last_run", "—"))

    st.dataframe(status_data, width="stretch", hide_index=True)

    # ── 新增排程 ────────────────────────────────
    st.divider()
    with st.expander("➕ 新增排程"):
        nc1, nc2, nc3 = st.columns(3)
        with nc1:
            new_name = st.text_input("排程名稱", placeholder="my_schedule")
        with nc2:
            new_cron = st.text_input("Cron 表達式", placeholder="0 8 * * 1-5")
        with nc3:
            new_wf = st.selectbox("工作流", workflow_options, key="new_wf")
        if st.button("新增排程", width="stretch"):
            if new_name and new_cron:
                try:
                    asyncio.run(scheduler.add_schedule(new_name, new_cron, new_wf))
                    st.success(f"已新增排程：{new_name}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"新增失敗：{exc}")
            else:
                st.warning("請填入排程名稱和 Cron 表達式")
