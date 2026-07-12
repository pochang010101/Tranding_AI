"""P-01 總覽儀表板 — 大盤環境 + 即時報價 + 持倉概覽 + 排程狀態。"""

from __future__ import annotations

import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card, regime_badge
from atlas.presentation.components.charts import gauge_chart, bar_chart
from atlas.presentation.service_container import (
    fetch_stock_data, fetch_stock_quote, get_indicator_lib,
    get_realtime_service, TW_TOP_STOCKS,
)


@st.fragment(run_every=30)
def _render_realtime_quotes() -> None:
    """每 30 秒自動重跑此 fragment，優先讀 RealtimePushService 快取，
    無快取時 fallback 到 fetch_stock_quote（TWSE MIS / yfinance）。"""
    top_codes = [code for code, _name in TW_TOP_STOCKS[:10]]
    name_map = dict(TW_TOP_STOCKS)
    quote_data: dict[str, list] = {"代碼": [], "名稱": [], "現價": [], "漲跌%": []}

    svc = get_realtime_service()
    # 確保這批代碼已被訂閱（重複訂閱安全）
    svc.subscribe(top_codes)

    for code in top_codes:
        try:
            q = svc.get_latest(code) or fetch_stock_quote(code)
            price = q["price"]
            prev = q["prev_close"]
            chg = (price - prev) / prev * 100 if prev else 0
            quote_data["代碼"].append(code)
            quote_data["名稱"].append(name_map.get(code, ""))
            quote_data["現價"].append(f"{price:,.1f}")
            quote_data["漲跌%"].append(f"{chg:+.2f}%")
        except Exception:
            continue

    if quote_data["代碼"]:
        source = "realtime" if svc.get_latest(top_codes[0]) else "cache"
        st.caption(f"資料來源：{source} | 自動更新每 30 秒")
        st.dataframe(quote_data, width="stretch", hide_index=True)
    else:
        st.info("報價載入中...")


def render() -> None:
    st.title("📊 總覽儀表板")
    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
<span class="legend-good">大盤指數漲跌</span>：&gt;0 多方走強、&lt;0 空方走弱，為當日市場方向依據<br>
<span class="legend-good">成交量</span>：&gt;2000億 市場熱絡、1000~2000億 正常、&lt;1000億 冷清觀望<br>
<span class="legend-warn">情緒分數（RSI）</span>：5 級制 — <span class="legend-bad">極度恐懼（&lt;30）</span>為逆勢買進機會、<span class="legend-good">極度貪婪（&gt;70）</span>需提高風險意識<br>
<span class="legend-warn">市場狀態</span>：<span class="legend-good">Bull 多頭趨勢</span>（MA8&gt;MA21 且收盤&gt;MA8）、<span class="legend-bad">Bear 空頭趨勢</span>（MA8&lt;MA21 且收盤&lt;MA8）、<span class="legend-warn">Range 盤整</span><br>
<span class="legend-good">排程狀態</span>：顯示盤前/盤中/盤後/月度重建各自動化任務的排定與執行情況
</div>
""", unsafe_allow_html=True)
    c = get_colors()
    market = st.session_state.get("market", "TW")

    # ── Row 1: 大盤環境（用加權指數 ^TWII 即時資料）──
    st.subheader("大盤環境")

    # 取加權指數資料判斷環境
    idx_df = fetch_stock_data("^TWII" if market == "TW" else "^GSPC", "3mo")
    regime_text, regime_status, regime_badge_val = "N/A", "neutral", "RANGE"
    sentiment_val = 50
    breadth_text = "—"
    adl_text = "—"

    if idx_df is not None and not idx_df.empty:
        lib = get_indicator_lib()
        idx_ind = lib.calculate_all(idx_df)

        # 判斷趨勢：MA8 > MA21 > MA55 → 多頭
        ma8 = idx_ind["MA8"].iloc[-1] if "MA8" in idx_ind.columns else 0
        ma21 = idx_ind["MA21"].iloc[-1] if "MA21" in idx_ind.columns else 0
        close = idx_df["close"].iloc[-1]

        if ma8 > ma21 and close > ma8:
            regime_text, regime_status, regime_badge_val = "多頭", "positive", "BULL"
        elif ma8 < ma21 and close < ma8:
            regime_text, regime_status, regime_badge_val = "空頭", "negative", "BEAR"
        else:
            regime_text, regime_status, regime_badge_val = "盤整", "neutral", "RANGE"

        # RSI 作為情緒指數
        rsi = idx_ind["RSI14"].iloc[-1] if "RSI14" in idx_ind.columns else 50
        sentiment_val = int(rsi) if rsi == rsi else 50  # NaN check

        # 漲跌幅
        prev = idx_df["close"].iloc[-2] if len(idx_df) >= 2 else close
        change_pct = (close - prev) / prev * 100 if prev else 0
        adl_text = f"{change_pct:+.2f}%"
        breadth_text = f"RSI={sentiment_val}"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(metric_card("大盤趨勢", regime_text, status=regime_status),
                    unsafe_allow_html=True)
        st.markdown(regime_badge(regime_badge_val), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card("情緒指數", str(sentiment_val),
                    status="positive" if sentiment_val > 55 else
                    "negative" if sentiment_val < 45 else "neutral"),
                    unsafe_allow_html=True)
    with col3:
        st.markdown(metric_card("技術指標", breadth_text, status="neutral"),
                    unsafe_allow_html=True)
    with col4:
        st.markdown(metric_card("大盤漲跌", adl_text,
                    status="positive" if "+" in adl_text else "negative" if "-" in adl_text else "neutral"),
                    unsafe_allow_html=True)

    st.markdown("""
    <div class="legend-box">
    <strong>指標說明</strong><br>
    <span class="legend-good">大盤趨勢</span>：MA8 &gt; MA21 且收盤 &gt; MA8 = <span class="legend-good">多頭</span>、反之 = <span class="legend-bad">空頭</span>、其餘 = <span class="legend-warn">盤整</span><br>
    <span class="legend-good">情緒指數</span>：以 RSI 衡量，<span class="legend-good">&gt;55 偏貪婪（多方）</span>、<span class="legend-bad">&lt;45 偏恐懼（空方）</span>、45~55 中性
    </div>
    """, unsafe_allow_html=True)

    # ── Row 2: 情緒儀表 + 權值股即時報價 ─────────
    st.divider()
    col_a, col_b = st.columns([1, 2])

    with col_a:
        st.subheader("情緒指數")
        fig = gauge_chart(sentiment_val, title="Fear & Greed", min_val=0, max_val=100)
        st.plotly_chart(fig, width="stretch")

    with col_b:
        st.subheader("權值股即時報價")
        _render_realtime_quotes()

    # ── Row 3: 持倉概覽 ────────────────────────
    st.divider()
    st.subheader("持倉概覽")

    # 從 session_state 讀取紙上交易持倉
    pt_positions = st.session_state.get("pt_positions", [])
    pt_orders = st.session_state.get("pt_orders", [])
    pt_capital = st.session_state.get("pt_capital", 1_000_000)
    eq = st.session_state.get("pt_equity_curve", [pt_capital])
    sell_orders = [o for o in pt_orders if o.get("方向") == "賣出"]
    total_pnl = sum(o.get("損益", 0) for o in sell_orders)
    wins = sum(1 for o in sell_orders if o.get("損益", 0) > 0)
    win_rate = wins / len(sell_orders) * 100 if sell_orders else 0

    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        st.markdown(metric_card("持倉數", str(len(pt_positions)), status="neutral"),
                    unsafe_allow_html=True)
    with col_p2:
        st.markdown(metric_card("累計損益", f"${total_pnl:+,.0f}",
                    status="positive" if total_pnl >= 0 else "negative"),
                    unsafe_allow_html=True)
    with col_p3:
        st.markdown(metric_card("交易次數", str(len(sell_orders)), status="neutral"),
                    unsafe_allow_html=True)
    with col_p4:
        st.markdown(metric_card("勝率", f"{win_rate:.1f}%",
                    status="positive" if win_rate >= 50 else "negative" if win_rate > 0 else "neutral"),
                    unsafe_allow_html=True)

    # ── Row 4: Top 5 權值股走勢 + 排程 ──────────
    st.divider()
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.subheader("Top 5 權值股 — RSI")
        rsi_labels, rsi_values = [], []
        for code, name in TW_TOP_STOCKS[:5]:
            try:
                df = fetch_stock_data(code, "3mo")
                if df is not None and not df.empty:
                    ind = get_indicator_lib().calculate_all(df)
                    rsi = ind["RSI14"].iloc[-1]
                    if rsi == rsi:  # NaN check
                        rsi_labels.append(f"{code}\n{name}")
                        rsi_values.append(round(rsi, 1))
            except Exception:
                continue
        if rsi_labels:
            fig = bar_chart(rsi_labels, rsi_values, title="RSI14", height=350)
            st.plotly_chart(fig, width="stretch")

    with col_c2:
        st.subheader("排程狀態")
        schedules = {
            "工作流": ["盤前 SOP", "盤中雷達", "盤後選股", "月度重建"],
            "執行時間": [
                "週一~五 08:00",
                "週一~五 09:00",
                "週一~五 13:45",
                "每週日 20:00",
            ],
            "用途說明": [
                "抓取隔夜國際行情→缺口預測→大盤環境→情緒評分",
                "啟動盤中即時雷達，偵測 11 種訊號（突破/量增/法人等）",
                "停雷達→更新收盤資料→全市場選股掃描→推送結果",
                "重建股票池：重算 RS 排名、產業輪動、因子權重",
            ],
            "狀態": ["⏳ 排程中", "⏳ 排程中", "⏳ 排程中", "⏳ 排程中"],
        }
        st.dataframe(schedules, use_container_width=True, hide_index=True)
        st.caption("非交易日自動跳過（月度重建除外）")

    # Footer
    st.divider()
    from datetime import datetime
    st.caption(f"市場：{market} | 更新時間：{datetime.now().strftime('%H:%M:%S')} | Atlas v5.0")
