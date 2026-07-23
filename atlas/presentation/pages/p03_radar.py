"""P-03 盤中雷達 — 即時訊號列表、偵測器統計、持倉損益。"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import bar_chart
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    fetch_stock_quote,
)

# 台股熱門觀察清單（預設）
_DEFAULT_WATCHLIST = [
    "2330", "2317", "2454", "2382", "2308",  # 電子權值
    "2881", "2882", "2884", "2886", "2891",  # 金融
    "2303", "2357", "3711", "2379", "3008",  # 科技
    "1301", "1303", "1326", "2002", "2105",  # 傳產
]


def render() -> None:
    st.title("📡 盤中雷達")
    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
<span class="legend-good">偵測器</span>：爆量啟動 / 大單異常 / 急拉急殺 / 均線跌破(突破) / 價量背離<br>
<span class="legend-warn">訊號強度（嚴重度）</span>：<span class="legend-good">3⭐ Strong — 立即關注</span>、<span class="legend-warn">2⭐ Medium — 列入觀察</span>、<span class="legend-bad">1⭐ Weak — 僅供參考</span><br>
<span class="legend-good">方向</span>：<span class="legend-good">BUY 買入訊號</span>、<span class="legend-bad">SELL 賣出/警示訊號</span>、<span class="legend-warn">ALERT 中性警示</span>
</div>
""", unsafe_allow_html=True)
    get_colors()

    # ── 掃描控制 ────────────────────────────────
    with st.expander("🔧 觀察名單與掃描", expanded=True):
        watchlist_input = st.text_area(
            "觀察名單（逗號分隔代碼）",
            value=", ".join(_DEFAULT_WATCHLIST),
            height=68,
        )
        codes = [c.strip() for c in watchlist_input.replace("\n", ",").split(",") if c.strip()]

        col_btn, col_info = st.columns([1, 3])
        with col_btn:
            scan_clicked = st.button("🔍 執行掃描", type="primary", use_container_width=True)
        with col_info:
            st.caption(f"將掃描 {len(codes)} 檔股票 × 5 偵測器（爆量/大單/急拉急殺/均線/價量背離）")

    # ── 執行掃描 ────────────────────────────────
    if scan_clicked and codes:
        from atlas.application.realtime_radar import scan_watchlist_sync

        with st.spinner(f"掃描 {len(codes)} 檔股票中…"):
            signals = scan_watchlist_sync(codes)
            st.session_state["radar_signals"] = signals

    signals: list[dict] = st.session_state.get("radar_signals", [])

    # ── 雷達狀態 ────────────────────────────────
    buy_count = sum(1 for s in signals if str(s.get("direction", "")).upper() == "BUY")
    sell_count = sum(1 for s in signals if str(s.get("direction", "")).upper() == "SELL")
    alert_count = sum(1 for s in signals if str(s.get("direction", "")).upper() == "ALERT")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            metric_card("今日告警", str(len(signals)), status="neutral"),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            metric_card("買入訊號", str(buy_count), status="positive"),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            metric_card("賣出訊號", str(sell_count), status="negative"),
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            metric_card("中性警示", str(alert_count), status="neutral"),
            unsafe_allow_html=True,
        )

    # ── 即時訊號列表 ────────────────────────────
    st.divider()
    st.subheader("訊號列表")

    if not signals:
        st.info("目前無訊號。按上方「執行掃描」開始掃描觀察名單。")
    else:
        direction_icon = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "ALERT": "🟡 ALERT"}

        rows = []
        for s in signals:
            raw_dir = str(s.get("direction", "")).upper()
            rows.append({
                "時間": s.get("time", ""),
                "偵測器": s.get("detector", ""),
                "代碼": s.get("code", ""),
                "名稱": s.get("name", ""),
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
            det_counter = Counter(
                s.get("detector", "") for s in signals if s.get("detector")
            )
            if det_counter:
                det_names, det_counts = zip(*det_counter.most_common(10), strict=False)
                fig = bar_chart(
                    list(det_names), list(det_counts),
                    title="今日觸發次數", horizontal=True, height=350,
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("無訊號資料。")
        else:
            st.info("無訊號資料。")

    with col_b:
        st.subheader("熱門標的")
        if signals:
            code_counter = Counter(
                s.get("code", "") for s in signals if s.get("code")
            )
            if code_counter:
                hot_codes, hot_counts = zip(*code_counter.most_common(10), strict=False)
                fig = bar_chart(
                    list(hot_codes), list(hot_counts),
                    title="觸發次數 by 標的", horizontal=True, height=350,
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("無訊號資料。")
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
