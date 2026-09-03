"""P-03 盤中雷達 — 即時訊號列表、偵測器統計、持倉損益。"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import timedelta

import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import bar_chart
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    fetch_stock_quote,
    get_realtime_service,
)

logger = logging.getLogger(__name__)

# ── 觀察股持久化路徑 ──
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "settings.local.json")


def _load_persisted_watchlist() -> list[str]:
    """從 settings.local.json 讀取觀察股清單。"""
    try:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("watchlist_codes", [])
    except Exception as exc:
        logger.warning("讀取持久化觀察股失敗：%s", exc)
    return []

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

    # ── 持久化恢復：session_state 無觀察股但檔案有 → 自動載入 ──
    try:
        if not st.session_state.get("watchlist_codes"):
            persisted = _load_persisted_watchlist()
            if persisted:
                st.session_state["watchlist_codes"] = persisted
    except Exception:
        pass

    # ── 觀察股摘要區（頁面頂部） ────────────────
    saved_watchlist: list[str] = st.session_state.get("watchlist_codes", [])
    if saved_watchlist:
        st.info(
            f"📋 目前觀察股 **{len(saved_watchlist)}** 檔："
            f" {', '.join(saved_watchlist[:20])}"
            f"{'…' if len(saved_watchlist) > 20 else ''}"
        )
    else:
        st.warning("尚無觀察股。請先至 **P-04 選股** 執行選股並加入觀察股，或在下方手動輸入代碼。")

    # ── 掃描控制 ────────────────────────────────
    with st.expander("🔧 觀察名單與掃描", expanded=True):
        # 從選股頁面載入觀察股
        col_load, col_load_info = st.columns([1, 3])
        with col_load:
            load_clicked = st.button(
                f"⭐ 從觀察股載入（{len(saved_watchlist)} 檔）",
                disabled=(len(saved_watchlist) == 0),
                width="stretch",
            )
            if load_clicked:
                st.session_state["radar_watchlist_input"] = ", ".join(saved_watchlist)
                st.session_state["radar_auto_scan_after_load"] = True
                st.rerun()
        with col_load_info:
            if saved_watchlist:
                st.caption(f"觀察股：{', '.join(saved_watchlist[:15])}{'…' if len(saved_watchlist) > 15 else ''}")
            else:
                st.caption("尚無觀察股，請先至 P-04 選股加入。")

        default_val = st.session_state.get("radar_watchlist_input", ", ".join(_DEFAULT_WATCHLIST))
        watchlist_input = st.text_area(
            "觀察名單（逗號分隔代碼）",
            value=default_val,
            height=68,
        )
        codes = [c.strip() for c in watchlist_input.replace("\n", ",").split(",") if c.strip()]

        col_btn, col_auto, col_info = st.columns([1, 1, 2])
        with col_btn:
            scan_clicked = st.button("🔍 執行掃描", type="primary", width="stretch")
        with col_auto:
            auto_refresh = st.toggle("⏱ 自動更新 (30s)", value=True, key="radar_auto_refresh")
        with col_info:
            st.caption(f"將掃描 {len(codes)} 檔股票 × 5 偵測器（爆量/大單/急拉急殺/均線/價量背離）")

    # ── 掃描函式 ────────────────────────────────
    def _do_scan(codes: list[str]) -> list[dict]:
        from datetime import datetime

        from atlas.application.realtime_radar import scan_watchlist_sync
        from atlas.constants import TW_TZ

        signals = scan_watchlist_sync(codes)
        st.session_state["radar_signals"] = signals
        st.session_state["radar_last_update"] = datetime.now(TW_TZ).strftime("%H:%M:%S")
        return signals

    # 載入觀察股後自動掃描
    auto_scan = st.session_state.pop("radar_auto_scan_after_load", False)

    # 手動掃描 或 載入後自動掃描
    if (scan_clicked or auto_scan) and codes:
        # 訂閱到 RealtimePushService（背景批次抓報價）
        try:
            rt_svc = get_realtime_service()
            rt_svc.subscribe(codes)
        except Exception as exc:
            logger.warning("RealtimePushService 訂閱失敗：%s", exc)

        with st.spinner(f"掃描 {len(codes)} 檔股票中…"):
            _do_scan(codes)

    # ── 訊號顯示 fragment（含自動更新） ─────────
    st.session_state["radar_codes"] = codes

    @st.fragment(run_every=timedelta(seconds=15) if (auto_refresh and codes) else None)
    def _realtime_quotes_panel():
        """即時報價面板 — 每 15 秒自動刷新，資料來自 RealtimePushService。"""
        try:
            rt_svc = get_realtime_service()
            all_quotes = rt_svc.get_all()
        except Exception:
            all_quotes = {}

        if not all_quotes:
            st.caption("等待即時報價資料…（掃描後自動訂閱）")
            return

        st.subheader(f"📊 即時報價（{len(all_quotes)} 檔）")

        rows = []
        for code, q in sorted(all_quotes.items()):
            price = q.get("price", 0)
            prev = q.get("prev_close", 0)
            change = price - prev if prev else 0
            change_pct = (change / prev * 100) if prev else 0

            rows.append({
                "代碼": code,
                "現價": price,
                "漲跌": change,
                "漲跌%": change_pct,
                "成交量": q.get("volume", 0),
                "最高": q.get("day_high", 0),
                "最低": q.get("day_low", 0),
            })

        quote_df = pd.DataFrame(rows)
        st.dataframe(
            quote_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "現價": st.column_config.NumberColumn(format="%.2f"),
                "漲跌": st.column_config.NumberColumn(format="%+.2f"),
                "漲跌%": st.column_config.NumberColumn(format="%+.2f%%"),
                "成交量": st.column_config.NumberColumn(format="%,d"),
                "最高": st.column_config.NumberColumn(format="%.2f"),
                "最低": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    _realtime_quotes_panel()

    @st.fragment(run_every=timedelta(seconds=30) if (auto_refresh and codes) else None)
    def _radar_results():
        # 自動更新時重新掃描
        if st.session_state.get("radar_auto_refresh") and st.session_state.get("radar_codes"):
            _do_scan(st.session_state["radar_codes"])

        signals: list[dict] = st.session_state.get("radar_signals", [])

        # ── 雷達狀態 ────────────────────────────
        buy_count = sum(1 for s in signals if str(s.get("direction", "")).upper() == "BUY")
        sell_count = sum(1 for s in signals if str(s.get("direction", "")).upper() == "SELL")
        alert_count = sum(1 for s in signals if str(s.get("direction", "")).upper() == "ALERT")

        last_update = st.session_state.get("radar_last_update", "")
        if last_update:
            st.caption(f"📡 最後更新：{last_update}")

        # ── RealtimePushService 狀態 ──────────────
        try:
            rt_svc = get_realtime_service()
            if rt_svc.is_running:
                st.caption(f"📡 即時報價服務運行中（{len(rt_svc.subscribed_codes())} 檔訂閱）")
            else:
                st.caption("⏸ 即時報價服務未啟動")
        except Exception:
            st.caption("⏸ 即時報價服務不可用")

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

        # ── 即時訊號列表 ────────────────────────
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

        # ── 偵測器統計 ──────────────────────────
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

    _radar_results()

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
