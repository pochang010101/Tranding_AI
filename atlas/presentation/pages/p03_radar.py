"""P-03 盤中雷達 — 即時訊號列表、偵測器統計、持倉損益、推播歷史。"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import bar_chart
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    TW_TOP_STOCKS,
    fetch_stock_data,
    fetch_stock_quote,
    get_indicator_lib,
)


def render() -> None:
    st.title("📡 盤中雷達")
    c = get_colors()

    # ── 雷達狀態 ────────────────────────────────
    radar_running: bool = st.session_state.get("radar_running", False)
    signals: list[dict] = st.session_state.get("radar_signals", [])

    buy_count = sum(1 for s in signals if str(s.get("direction", "")).upper() == "BUY")
    sell_count = sum(1 for s in signals if str(s.get("direction", "")).upper() == "SELL")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        status_label = "🟢 執行中" if radar_running else "🔴 已停止"
        status_color = "positive" if radar_running else "negative"
        st.markdown(metric_card("雷達狀態", status_label, status=status_color), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card("今日告警", str(len(signals)), status="neutral"), unsafe_allow_html=True)
    with col3:
        st.markdown(metric_card("買入訊號", str(buy_count), status="positive"), unsafe_allow_html=True)
    with col4:
        st.markdown(metric_card("賣出訊號", str(sell_count), status="negative"), unsafe_allow_html=True)

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

    if not signals:
        st.info("目前無訊號。雷達啟動後訊號將即時顯示於此。")
    else:
        direction_icon = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "ALERT": "🟡 ALERT"}

        rows = []
        for s in signals:
            raw_dir = str(s.get("direction", "")).upper()
            rows.append({
                "時間": s.get("time", ""),
                "偵測器": s.get("detector", ""),
                "代碼": s.get("code", ""),
                "方向": direction_icon.get(raw_dir, raw_dir),
                "觸發價": s.get("price"),
                "嚴重度": s.get("severity", 1),
                "細節": s.get("detail", ""),
            })

        signals_df = pd.DataFrame(rows)
        st.dataframe(
            signals_df,
            width="stretch",
            hide_index=True,
            column_config={
                "嚴重度": st.column_config.NumberColumn(format="%d ⭐"),
            },
        )

    # ── 偵測器統計 ──────────────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("偵測器觸發統計")
        if signals:
            det_counter = Counter(s.get("detector", "") for s in signals if s.get("detector"))
            det_names, det_counts = zip(*det_counter.most_common(10)) if det_counter else ([], [])
            fig = bar_chart(list(det_names), list(det_counts), title="今日觸發次數",
                            horizontal=True, height=350)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("無訊號資料。")

    with col_b:
        st.subheader("熱門標的")
        if signals:
            code_counter = Counter(s.get("code", "") for s in signals if s.get("code"))
            hot_codes, hot_counts = zip(*code_counter.most_common(10)) if code_counter else ([], [])
            fig = bar_chart(list(hot_codes), list(hot_counts), title="觸發次數 by 標的",
                            horizontal=True, height=350)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("無訊號資料。")

    # ── 持倉即時損益 ────────────────────────────
    st.divider()
    st.subheader("持倉即時損益")

    pt_positions: list[dict] = st.session_state.get("pt_positions", [])

    if not pt_positions:
        st.info("目前無持倉。")
    else:
        rows = []
        for pos in pt_positions:
            code = str(pos.get("代碼", ""))
            name = pos.get("名稱", code)
            entry_price = float(pos.get("進場價", 0) or 0)
            lots = int(pos.get("張數", 0) or 0)
            stop_loss = pos.get("停損")
            take_profit = pos.get("停利")

            quote = fetch_stock_quote(code)
            current_price = quote.get("price", 0) or entry_price

            # 每張 = 1000 股
            pnl = (current_price - entry_price) * lots * 1000
            pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price else 0
            r_multiple = None
            if stop_loss and entry_price and entry_price != float(stop_loss):
                risk_per_share = entry_price - float(stop_loss)
                if risk_per_share != 0:
                    r_multiple = round((current_price - entry_price) / risk_per_share, 2)

            rows.append({
                "代碼": code,
                "名稱": name,
                "進場價": entry_price,
                "現價": current_price,
                "張數": lots,
                "停損": stop_loss,
                "停利": take_profit,
                "未實現損益": round(pnl),
                "損益%": round(pnl_pct, 2),
                "R倍數": r_multiple,
            })

        positions_df = pd.DataFrame(rows)
        st.dataframe(
            positions_df,
            width="stretch",
            hide_index=True,
            column_config={
                "損益%": st.column_config.NumberColumn(format="%+.2f%%"),
                "未實現損益": st.column_config.NumberColumn(format="$%+,d"),
            },
        )
