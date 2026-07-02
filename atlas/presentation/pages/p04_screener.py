"""P-04 每日選股 — 四主軸+三面向明細、精選清單、產業分佈。"""

from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)

# ── 產業分類 ────────────────────────────────────────────────────────────────
_INDUSTRY_MAP: dict[str, str] = {
    "2330": "半導體", "2454": "半導體", "2303": "半導體", "3711": "半導體",
    "3008": "光電", "2395": "科技",
    "2317": "電子製造", "2382": "電子製造", "2357": "電子製造",
    "2308": "電子零件",
    "2881": "金融", "2882": "金融", "2891": "金融", "2886": "金融",
    "2884": "金融", "2892": "金融", "5880": "金融", "2880": "金融",
    "2885": "金融",
    "2412": "電信", "3045": "電信", "4904": "電信",
    "1301": "石化", "1303": "石化", "6505": "石化",
    "2002": "鋼鐵",
    "2603": "航運",
    "1216": "食品", "2912": "食品",
    "2207": "汽車",
}

_LEVEL_ORDER = {"Lv5": 5, "Lv4": 4, "Lv3": 3, "Lv2": 2, "Lv1": 1, "Lv0": 0}


def _score_from_indicators(ind: pd.Series) -> dict:
    """從最後一列指標值計算簡易評分（不需完整 ScoringEngine 依賴鏈）。"""
    rsi = ind.get("RSI14", 50)
    macd_hist = ind.get("MACD_hist", 0)
    k = ind.get("K9", 50)
    close = ind.get("close", 0)
    ma21 = ind.get("MA21", close)
    ma55 = ind.get("MA55", close)

    # 技術面：RSI 40-70 + 收盤 > MA21 + MACD hist > 0
    tech_score = 0
    if 40 <= rsi <= 75:
        tech_score += 35
    elif rsi < 30:
        tech_score += 10  # 超賣，可能反彈
    if close > ma21 and ma21 > 0:
        tech_score += 35
    if macd_hist > 0:
        tech_score += 30

    # 動能面：KD + MA 排列
    momentum_score = 0
    if k > 50:
        momentum_score += 50
    if ma21 > ma55 and ma55 > 0:
        momentum_score += 50

    # 簡易個股 RS（用 RSI 替代）
    rs_score = min(100, max(0, rsi))

    # 主軸總分（等權平均）
    total = round((tech_score * 0.5 + momentum_score * 0.3 + rs_score * 0.2), 1)

    # 三面向判定（簡化）
    tech_ok = tech_score >= 60
    fund_ok = close > ma55 and ma55 > 0  # 長線趨勢為基本面替代
    chip_ok = macd_hist > 0 and k > 40   # 籌碼替代

    # 結論等級
    positive_aspects = sum([tech_ok, fund_ok, chip_ok])
    if total >= 75 and positive_aspects >= 2:
        level = "Lv5"
    elif total >= 62 and positive_aspects >= 2:
        level = "Lv4"
    elif total >= 50 and positive_aspects >= 2:
        level = "Lv3"
    elif total >= 38:
        level = "Lv2"
    else:
        level = "Lv1"

    return {
        "主軸總分": total,
        "技術分": tech_score,
        "動能分": momentum_score,
        "個股RS": round(rs_score, 1),
        "技術面": "🟢" if tech_ok else "⚪",
        "基本面": "🟢" if fund_ok else "⚪",
        "籌碼面": "🟢" if chip_ok else "⚪",
        "結論": level,
        "RSI14": round(rsi, 1) if pd.notna(rsi) else "—",
        "MACD柱": round(macd_hist, 3) if pd.notna(macd_hist) else "—",
        "K值": round(k, 1) if pd.notna(k) else "—",
    }


@st.cache_data(ttl=600, show_spinner=False)
def _run_scan(stock_list: list[tuple[str, str]]) -> pd.DataFrame:
    """掃描所有股票並回傳結果 DataFrame（快取 10 分鐘）。"""
    lib = get_indicator_lib()
    rows = []

    for code, name in stock_list:
        try:
            df = fetch_stock_data(code, "6mo")
            if df is None or df.empty or len(df) < 30:
                continue

            ind_df = lib.calculate_all(df)
            last = ind_df.iloc[-1]

            scores = _score_from_indicators(last)
            quote = fetch_stock_quote(code)
            price = quote.get("price", last["close"])
            prev = quote.get("prev_close", 0)
            chg_pct = ((price - prev) / prev * 100) if prev > 0 else 0.0

            rows.append({
                "代碼": code,
                "名稱": name,
                "產業": _INDUSTRY_MAP.get(code, "其他"),
                "現價": round(price, 2),
                "漲跌%": round(chg_pct, 2),
                **scores,
            })
        except Exception as exc:
            logger.warning("Skip %s (%s): %s", code, name, exc)

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result = result.sort_values("主軸總分", ascending=False).reset_index(drop=True)
    result.insert(0, "排名", range(1, len(result) + 1))
    return result


def render() -> None:
    st.title("🔍 每日選股")
    c = get_colors()  # noqa: F841 — keep for theme consistency

    # ── 控制列 ──────────────────────────────────
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        scan_date = st.date_input("掃描日期", value=None)  # noqa: F841
    with col2:
        top_n = st.selectbox("顯示筆數", [10, 20, 30, 50], index=1)
    with col3:
        min_level = st.selectbox("最低等級", ["Lv5", "Lv4", "Lv3", "Lv2", "Lv1", "全部"], index=2)

    run_btn = st.button("🔍 執行掃描", type="primary", use_container_width=True)

    if run_btn:
        st.session_state["scan_result"] = None  # 清除快取結果，強制重新掃描
        _run_scan.clear()

    # ── 即時報價預覽 ─────────────────────────────
    st.divider()
    st.subheader("市場快照（前 5 大權值股）")
    quote_cols = st.columns(5)
    preview_stocks = TW_TOP_STOCKS[:5]

    for col, (code, name) in zip(quote_cols, preview_stocks):
        try:
            q = fetch_stock_quote(code)
            price = q.get("price", 0)
            prev = q.get("prev_close", 0)
            chg = price - prev
            chg_pct = (chg / prev * 100) if prev > 0 else 0.0
            status = "positive" if chg >= 0 else "negative"
            sign = "+" if chg >= 0 else ""
            label = f"{name} ({code})"
            value = f"${price:,.1f}"
            delta = f"{sign}{chg_pct:.2f}%"
            with col:
                st.markdown(metric_card(label, value, delta=delta, status=status),
                            unsafe_allow_html=True)
        except Exception:
            with col:
                st.markdown(metric_card(f"{name} ({code})", "—", status="neutral"),
                            unsafe_allow_html=True)

    # ── 執行掃描或使用快取 ───────────────────────
    scan_result: pd.DataFrame | None = st.session_state.get("scan_result")

    if run_btn or scan_result is None:
        with st.spinner(f"正在掃描 {len(TW_TOP_STOCKS)} 支股票，請稍候…"):
            scan_result = _run_scan(TW_TOP_STOCKS)
            st.session_state["scan_result"] = scan_result

    if scan_result is None or scan_result.empty:
        st.warning("掃描無結果，請檢查網路連線或稍後再試。")
        return

    # ── 掃描統計 ────────────────────────────────
    st.divider()
    st.subheader("掃描結果統計")

    total_scanned = len(TW_TOP_STOCKS)
    passed = len(scan_result)
    lv3_plus = len(scan_result[scan_result["結論"].map(lambda x: _LEVEL_ORDER.get(x, 0) >= 3)])
    lv5_count = len(scan_result[scan_result["結論"] == "Lv5"])

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card("掃描標的", str(total_scanned), status="neutral"),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("成功取得", str(passed), status="positive"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("Lv3 以上", str(lv3_plus), status="positive"),
                    unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("Lv5 精選", str(lv5_count),
                                status="positive" if lv5_count > 0 else "neutral"),
                    unsafe_allow_html=True)

    # ── 精選清單表格 ────────────────────────────
    st.divider()
    st.subheader("精選清單（依主軸總分排序）")

    display_df = scan_result.copy()

    # 篩選最低等級
    if min_level != "全部":
        min_val = _LEVEL_ORDER.get(min_level, 0)
        display_df = display_df[
            display_df["結論"].map(lambda x: _LEVEL_ORDER.get(x, 0) >= min_val)
        ]

    table_cols = [
        "排名", "代碼", "名稱", "產業", "現價", "漲跌%",
        "主軸總分", "技術分", "動能分", "個股RS",
        "RSI14", "MACD柱", "K值",
        "技術面", "基本面", "籌碼面", "結論",
    ]
    # 只顯示存在的欄位
    table_cols = [c for c in table_cols if c in display_df.columns]

    st.dataframe(
        display_df[table_cols].head(top_n),
        use_container_width=True,
        hide_index=True,
        column_config={
            "主軸總分": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
            "技術分":   st.column_config.ProgressColumn(min_value=0, max_value=100),
            "動能分":   st.column_config.ProgressColumn(min_value=0, max_value=100),
            "個股RS":   st.column_config.ProgressColumn(min_value=0, max_value=100),
            "漲跌%":    st.column_config.NumberColumn(format="%.2f%%"),
            "現價":     st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    # ── 圖表區 ──────────────────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    top5 = display_df.head(5)

    with col_a:
        st.subheader("四主軸總分 — Top 5")
        if not top5.empty:
            fig = bar_chart(
                labels=top5["名稱"].tolist(),
                values=top5["主軸總分"].tolist(),
                title="主軸總分排行",
                height=350,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("無足夠資料顯示圖表")

    with col_b:
        st.subheader("產業分佈")
        if "產業" in display_df.columns and not display_df.empty:
            industry_counts = display_df["產業"].value_counts()
            fig = bar_chart(
                labels=industry_counts.index.tolist(),
                values=industry_counts.values.tolist(),
                title="精選清單產業分佈",
                horizontal=True,
                height=350,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("無產業資料")

    # ── 漲跌分佈 ────────────────────────────────
    if "漲跌%" in display_df.columns and not display_df.empty:
        st.divider()
        st.subheader("漲跌幅分佈")
        sorted_df = display_df.sort_values("漲跌%", ascending=False).head(top_n)
        colors = ["#26c6da" if v >= 0 else "#ef5350" for v in sorted_df["漲跌%"]]
        import plotly.graph_objects as go
        fig_chg = go.Figure(go.Bar(
            x=sorted_df["名稱"].tolist(),
            y=sorted_df["漲跌%"].tolist(),
            marker_color=colors,
            text=[f"{v:+.2f}%" for v in sorted_df["漲跌%"]],
            textposition="outside",
        ))
        fig_chg.update_layout(
            title="漲跌幅（%）",
            height=320,
            margin=dict(l=0, r=0, t=40, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e0e0e0"),
            xaxis=dict(showgrid=False),
            yaxis=dict(zeroline=True, zerolinecolor="#555"),
        )
        st.plotly_chart(fig_chg, use_container_width=True)

    # ── 匯出按鈕 ────────────────────────────────
    st.divider()
    col_e1, col_e2 = st.columns([3, 1])
    with col_e2:
        csv = display_df[table_cols].head(top_n).to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 匯出 CSV", csv, "scan_result.csv", "text/csv",
                           use_container_width=True)
