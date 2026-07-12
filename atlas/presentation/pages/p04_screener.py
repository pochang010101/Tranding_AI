"""P-04 每日選股 — 全市場智慧篩選：法人買賣、量能、價格動能。"""

from __future__ import annotations

import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from atlas.presentation.components.charts import bar_chart
from atlas.presentation.components.theme import get_colors, metric_card

logger = logging.getLogger(__name__)


def _run_smart_scan() -> tuple[pd.DataFrame, str]:
    """執行全市場智慧掃描（快取 10 分鐘）。回傳 (DataFrame, 資料日期字串)。"""
    from atlas.application.smart_screener import SmartScreener

    screener = SmartScreener(
        min_price=st.session_state.get("scr_min_price", 10.0),
        min_volume_lots=st.session_state.get("scr_min_vol", 500),
    )
    df = screener.scan_to_dataframe()
    trading_date = screener.get_trading_date()
    date_str = trading_date.strftime("%Y-%m-%d") if trading_date else "未知"
    return df, date_str


def render() -> None:
    st.title("🔍 每日選股")
    c = get_colors()

    # ── 圖例說明 ──
    st.markdown("""
    <div class="legend-box">
    <strong>選股邏輯</strong>：掃描 TWSE + TPEx 全市場 → 去除水餃股/冷門股/處置股 → 依法人買賣、量能、漲跌篩選<br>
    <strong>訊號標籤</strong>：
    <span class="legend-good">外資買超</span> 外資淨買入 |
    <span class="legend-good">投信買超</span> 投信淨買入（最具指標性）|
    <span class="legend-good">雙法人</span> 外資+投信同時買 |
    <span class="legend-good">大買</span> 大額買超 |
    <span class="legend-good">大量/爆量</span> 成交量異常放大 |
    <span class="legend-good">強勢</span> 漲幅≥3% |
    <span class="legend-warn">漲停</span> 漲幅≥9.5% |
    <span class="legend-good">熱門題材</span> 屬於當日漲幅領先的概念股 |
    <span class="legend-good">多題材交集</span> 同時屬於2個以上熱門題材<br>
    <strong>選股分數</strong>：分數越高表示多個正面訊號同時出現，<span class="legend-good">≥50 強烈推薦</span>、<span class="legend-warn">30~50 值得關注</span>、<span class="legend-bad">&lt;30 單一訊號</span><br>
    <strong>RSI(14)</strong>：相對強弱指標，<span class="legend-bad">&gt;70 超買</span>、50 多空平衡、<span class="legend-good">&lt;30 超賣反彈機會</span>
    </div>
    """, unsafe_allow_html=True)

    # ── 控制列 ──
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        min_price = st.number_input("最低股價", value=20.0, step=5.0, key="scr_min_price")
    with col2:
        min_vol = st.number_input("最低成交量(張)", value=1000, step=100, key="scr_min_vol")
    with col3:
        top_n = st.selectbox("顯示筆數", [20, 50, 100, 200], index=1)

    col4, col5 = st.columns(2)
    with col4:
        tag_filter = st.multiselect(
            "篩選標籤",
            ["外資買超", "投信買超", "雙法人", "外資大買", "投信大買",
             "大量", "爆量", "強勢", "漲停", "熱門題材", "多題材交集"],
            default=[],
        )
    with col5:
        from atlas.strategy.theme_catalog import THEME_MAP
        theme_filter = st.multiselect(
            "篩選題材",
            sorted(THEME_MAP.keys()),
            default=[],
        )

    run_btn = st.button("🔍 執行全市場掃描", type="primary", use_container_width=True)

    # ── 執行掃描 ──
    if run_btn:
        st.session_state["smart_scan_result"] = None

    scan_result: pd.DataFrame | None = st.session_state.get("smart_scan_result")

    if run_btn or scan_result is None:
        with st.spinner("正在掃描全市場（TWSE + TPEx），約需 10~30 秒…"):
            try:
                scan_result, data_date = _run_smart_scan()
                st.session_state["smart_scan_result"] = scan_result
                st.session_state["smart_scan_date"] = data_date
                # 同步取得熱門題材
                try:
                    from atlas.infrastructure.twse_bulk import fetch_twse_daily_all
                    from atlas.strategy.theme_catalog import detect_hot_themes
                    daily_df = fetch_twse_daily_all()
                    hot = detect_hot_themes(daily_df)
                    st.session_state["hot_themes_data"] = [
                        {"name": t.name, "avg": t.avg_change_pct,
                         "up": t.up_count, "total": t.stock_count,
                         "top": t.top_stocks, "score": t.heat_score}
                        for t in hot
                    ]
                except Exception:
                    st.session_state["hot_themes_data"] = []
            except Exception as exc:
                st.error(f"掃描失敗：{exc}")
                st.info("可能原因：非交易時段、API 暫時無法連線。請稍後再試。")
                return

    if scan_result is None or scan_result.empty:
        st.warning("掃描無結果。可能原因：API 尚未更新或篩選條件過嚴。")
        return

    # 顯示資料日期（非交易日會自動回退至最近交易日）
    data_date = st.session_state.get("smart_scan_date", "")
    if data_date:
        st.info(f"📅 資料日期：**{data_date}**（非交易日自動取得最近交易日資料）")

    # ── 標籤 + 題材篩選 ──
    display_df = scan_result.copy()
    if tag_filter:
        mask = display_df["訊號標籤"].apply(
            lambda tags: any(t in tags for t in tag_filter)
        )
        display_df = display_df[mask]
    if theme_filter:
        mask = display_df["題材"].apply(
            lambda themes: any(t in str(themes) for t in theme_filter)
        )
        display_df = display_df[mask]

    if display_df.empty:
        st.warning("沒有符合所選條件的結果。")
        return

    # 重新編排名
    display_df = display_df.reset_index(drop=True)
    display_df["排名"] = range(1, len(display_df) + 1)

    # ── 掃描統計 ──
    st.divider()
    st.subheader("掃描結果統計")

    total_hits = len(display_df)
    dual_inst = len(display_df[display_df["訊號標籤"].str.contains("雙法人", na=False)])
    foreign_buy = len(display_df[display_df["訊號標籤"].str.contains("外資買超", na=False)])
    trust_buy = len(display_df[display_df["訊號標籤"].str.contains("投信買超", na=False)])
    high_score = len(display_df[display_df["選股分數"] >= 50])

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(metric_card("選股命中", str(total_hits), status="positive"),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("雙法人", str(dual_inst),
                    status="positive" if dual_inst > 0 else "neutral"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("外資買超", str(foreign_buy), status="positive"),
                    unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("投信買超", str(trust_buy), status="positive"),
                    unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card("高分(≥50)", str(high_score),
                    status="positive" if high_score > 0 else "neutral"),
                    unsafe_allow_html=True)

    # ── 熱門題材 ──
    hot_themes_data = st.session_state.get("hot_themes_data")
    if hot_themes_data:
        st.divider()
        st.subheader("🔥 今日熱門題材")
        theme_cols = st.columns(min(5, len(hot_themes_data)))
        for i, th in enumerate(hot_themes_data[:5]):
            with theme_cols[i]:
                status = "positive" if th["avg"] >= 1.0 else "warning" if th["avg"] >= 0 else "negative"
                st.markdown(metric_card(
                    th["name"], f"{th['avg']:+.1f}%",
                    delta=f"{th['up']}/{th['total']} 上漲",
                    status=status,
                ), unsafe_allow_html=True)

    # ── 結果表格 ──
    st.divider()
    st.subheader(f"選股清單（共 {len(display_df)} 檔，顯示前 {min(top_n, len(display_df))} 檔）")

    show_df = display_df.head(top_n)

    st.dataframe(
        show_df,
        use_container_width=True,
        hide_index=True,
        height=min(600, 40 + len(show_df) * 35),
        column_config={
            "選股分數": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "RSI": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "漲跌%": st.column_config.NumberColumn(format="%+.2f%%"),
            "收盤": st.column_config.NumberColumn(format="$%.2f"),
            "成交量(張)": st.column_config.NumberColumn(format="%d"),
            "外資(張)": st.column_config.NumberColumn(format="%+d"),
            "投信(張)": st.column_config.NumberColumn(format="%+d"),
            "法人合計(張)": st.column_config.NumberColumn(format="%+d"),
        },
    )

    # ── 圖表區 ──
    st.divider()
    col_a, col_b = st.columns(2)

    top10 = show_df.head(10)

    with col_a:
        st.subheader("選股分數 — Top 10")
        if not top10.empty:
            labels = [f"{r['代碼']}\n{r['名稱']}" for _, r in top10.iterrows()]
            fig = bar_chart(
                labels=labels,
                values=top10["選股分數"].tolist(),
                title="選股分數排行",
                height=350,
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("法人買賣超 — Top 10")
        if not top10.empty:
            labels = [f"{r['代碼']}\n{r['名稱']}" for _, r in top10.iterrows()]
            foreign_vals = top10["外資(張)"].tolist()
            trust_vals = top10["投信(張)"].tolist()

            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=labels, y=foreign_vals, name="外資",
                marker_color="#2196f3",
                text=[f"{v:+d}" for v in foreign_vals],
                textposition="outside",
            ))
            fig2.add_trace(go.Bar(
                x=labels, y=trust_vals, name="投信",
                marker_color="#ff9800",
                text=[f"{v:+d}" for v in trust_vals],
                textposition="outside",
            ))
            fig2.update_layout(
                title="外資 vs 投信 買賣超 (張)",
                barmode="group",
                height=350,
                margin=dict(l=0, r=0, t=40, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e0e0e0"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            fig2.add_hline(y=0, line_color="#555")
            st.plotly_chart(fig2, use_container_width=True)

    # ── 訊號標籤分佈 ──
    st.divider()
    st.subheader("訊號標籤分佈")

    all_tags: dict[str, int] = {}
    for tags_str in display_df["訊號標籤"]:
        for tag in str(tags_str).split(" | "):
            tag = tag.strip()
            if tag:
                all_tags[tag] = all_tags.get(tag, 0) + 1

    if all_tags:
        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
        tag_names = [t[0] for t in sorted_tags]
        tag_counts = [t[1] for t in sorted_tags]

        tag_colors = {
            "外資買超": "#2196f3", "外資大買": "#1565c0",
            "投信買超": "#ff9800", "投信大買": "#e65100",
            "雙法人": "#4caf50",
            "大量": "#9c27b0", "爆量": "#7b1fa2",
            "強勢": "#00bcd4", "上漲": "#26c6da",
            "漲停": "#f44336",
        }
        colors = [tag_colors.get(t, "#78909c") for t in tag_names]

        fig3 = go.Figure(go.Bar(
            x=tag_names, y=tag_counts,
            marker_color=colors,
            text=[str(c) for c in tag_counts],
            textposition="outside",
        ))
        fig3.update_layout(
            title="各訊號觸發次數",
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e0e0e0"),
            xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig3, use_container_width=True)

    # ── 匯出 + LINE 推送 ──
    st.divider()
    col_e1, col_e2, col_e3 = st.columns([2, 1, 1])
    with col_e2:
        csv = display_df.head(top_n).to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 匯出 CSV", csv, "smart_scan_result.csv", "text/csv",
                           use_container_width=True)
    with col_e3:
        if st.button("📲 推送到 LINE", use_container_width=True, type="primary"):
            _push_to_line(display_df.head(top_n))


def _push_to_line(df: pd.DataFrame) -> None:
    """將選股結果格式化後推送到 LINE。"""
    from datetime import datetime
    from atlas.infrastructure.notifications.line import send_line_message_sync

    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    lines = [f"📊 Atlas 選股結果 ({now})", f"共 {len(df)} 檔命中", ""]

    for _, row in df.head(20).iterrows():
        code = row["代碼"]
        name = row["名稱"]
        close = row["收盤"]
        chg = row["漲跌%"]
        sign = "+" if chg >= 0 else ""
        tags = row["訊號標籤"]
        score = row["選股分數"]
        foreign = row.get("外資(張)", 0)
        trust = row.get("投信(張)", 0)

        themes = row.get("題材", "")

        line = f"{'🔴' if chg >= 3 else '🟢' if chg >= 0 else '🔵'} {code} {name}"
        line += f" ${close:.0f} ({sign}{chg:.1f}%)"
        if foreign:
            line += f" 外{foreign:+d}"
        if trust:
            line += f" 投{trust:+d}"
        line += f"\n  ⭐{score:.0f} {tags}"
        if themes and themes != "—":
            line += f"\n  📌{themes}"
        lines.append(line)

    if len(df) > 20:
        lines.append(f"\n...還有 {len(df) - 20} 檔，請至系統查看完整清單")

    msg = "\n".join(lines)
    ok = send_line_message_sync(msg)
    if ok:
        st.success("已推送到 LINE！")
    else:
        st.error("LINE 推送失敗，請確認 .env 中的 LINE_CHANNEL_ACCESS_TOKEN 是否正確。")
