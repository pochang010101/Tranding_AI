"""P-04 每日選股 — 全市場智慧篩選：法人買賣、量能、價格動能。"""

from __future__ import annotations

import logging
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from atlas.presentation.components.charts import bar_chart
from atlas.presentation.components.theme import get_colors, metric_card

logger = logging.getLogger(__name__)

# ── 觀察股持久化 ──────────────────────────────
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "settings.local.json")


def _persist_watchlist(codes: list[str]) -> None:
    """將觀察股清單寫入 settings.local.json 作為持久化備份。"""
    try:
        import json
        data: dict = {}
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
        data["watchlist_codes"] = codes
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("持久化觀察股失敗：%s", exc)


def _load_persisted_watchlist() -> list[str]:
    """從 settings.local.json 讀取觀察股清單。"""
    try:
        import json
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("watchlist_codes", [])
    except Exception as exc:
        logger.warning("讀取持久化觀察股失敗：%s", exc)
    return []


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


# ── 入口 ──────────────────────────────────────

def render() -> None:
    market = st.session_state.get("market", "TW")
    if market == "US":
        st.title("🔍 美股選股")
        _render_us_screener()
    else:
        st.title("🔍 每日選股")
        _render_tw_screener()


# ══════════════════════════════════════════════
# 台股選股（原有邏輯，不做任何修改）
# ══════════════════════════════════════════════

def _render_tw_screener() -> None:
    get_colors()

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
    <strong>RSI(14)</strong>：相對強弱指標，<span class="legend-bad">&gt;70 超買</span>、50 多空平衡、<span class="legend-good">&lt;30 超賣反彈機會</span><br>
    <strong>均線排列</strong>：<span class="legend-good">多頭</span> MA8&gt;MA21&gt;MA55 | <span class="legend-bad">空頭</span> MA8&lt;MA21&lt;MA55 | 糾結 其他<br>
    <strong>MA位置</strong>：<span class="legend-good">站上全部</span> 價格在MA8/21/55之上 | <span class="legend-warn">站上短均</span> 僅站上部分 | <span class="legend-bad">均線下方</span><br>
    <strong>扣抵方向</strong>：<span class="legend-good">全揚升</span> MA8/21/55均將上彎 | <span class="legend-warn">短揚長彎</span> 短均揚長均彎 | <span class="legend-bad">全下彎</span>
    </div>
    """, unsafe_allow_html=True)

    # ── 控制列 ──
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.number_input("最低股價", value=20.0, step=5.0, key="scr_min_price")
    with col2:
        st.number_input("最低成交量(張)", value=1000, step=100, key="scr_min_vol")
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

    # ── 均線 / 扣抵值篩選 ──
    col6, col7, col8 = st.columns(3)
    with col6:
        filter_ma_bull = st.checkbox("僅顯示均線多頭排列", key="scr_ma_bull")
    with col7:
        filter_above_ma55 = st.checkbox("僅顯示站上 MA55", key="scr_above_ma55")
    with col8:
        filter_ded_bull = st.checkbox("僅顯示扣抵值偏多（MA21 將揚升）", key="scr_ded_bull")

    run_btn = st.button("🔍 執行全市場掃描", type="primary", width="stretch")

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

    # 顯示資料日期（非交易日或盤中會自動回退至最近交易日）
    data_date = st.session_state.get("smart_scan_date", "")
    if data_date:
        from datetime import date as _date
        today_str = _date.today().strftime("%Y-%m-%d")
        if data_date == today_str:
            st.success(f"📅 資料日期：**{data_date}**（今日收盤資料）")
        else:
            st.warning(
                f"📅 資料日期：**{data_date}**（非今日資料）\n\n"
                "⚠️ 今日收盤資料尚未更新（TWSE 通常於 **15:00 後**發布），目前使用最近交易日資料。"
            )

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

    # ── 均線 / 扣抵值篩選 ──
    if filter_ma_bull and "均線排列" in display_df.columns:
        display_df = display_df[display_df["均線排列"] == "多頭"]
    if filter_above_ma55 and "MA位置" in display_df.columns:
        display_df = display_df[display_df["MA位置"].isin(["站上全部", "站上短均"])]
    if filter_ded_bull and "扣抵方向" in display_df.columns:
        display_df = display_df[display_df["扣抵方向"].isin(["全揚升", "短揚長彎"])]

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

    # ── 觀察股操作區（表格上方） ──
    existing_watchlist: list[str] = st.session_state.get("watchlist_codes", [])
    col_w0, col_w1, col_w2, col_w3, col_w4 = st.columns([0.5, 1, 1, 1, 2])
    with col_w0:
        select_all = st.checkbox("全選", key="screener_select_all")
    with col_w1:
        add_watchlist_btn = st.button("⭐ 加入觀察股", type="primary", width="stretch")
    with col_w2:
        add_all_btn = st.button("⭐ 全選加入觀察股", width="stretch")
    with col_w3:
        if existing_watchlist and st.button("🗑 清空觀察股", width="stretch"):
            st.session_state["watchlist_codes"] = []
            _persist_watchlist([])
            st.rerun()
    with col_w4:
        if existing_watchlist:
            st.info(f"觀察股 {len(existing_watchlist)} 檔：{', '.join(existing_watchlist[:10])}{'…' if len(existing_watchlist) > 10 else ''}")
        else:
            st.caption("勾選下方表格左側「觀察」欄，再點加入觀察股；或直接點「全選加入觀察股」。")

    show_df = display_df.head(top_n).copy()

    # 加入勾選欄供用戶選擇觀察股（全選時預設 True）
    show_df.insert(0, "觀察", select_all)

    edited_df = st.data_editor(
        show_df,
        width="stretch",
        hide_index=True,
        height=min(600, 40 + len(show_df) * 35),
        column_config={
            "觀察": st.column_config.CheckboxColumn("觀察", default=False, width="small"),
            "選股分數": st.column_config.ProgressColumn(min_value=0, max_value=130, format="%.0f"),
            "RSI": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "均線分數": st.column_config.ProgressColumn(min_value=0, max_value=15, format="%.0f"),
            "扣抵分數": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.0f"),
            "漲跌%": st.column_config.NumberColumn(format="%+.2f%%"),
            "收盤": st.column_config.NumberColumn(format="$%.2f"),
            "成交量(張)": st.column_config.NumberColumn(format="%d"),
            "外資(張)": st.column_config.NumberColumn(format="%+d"),
            "投信(張)": st.column_config.NumberColumn(format="%+d"),
            "法人合計(張)": st.column_config.NumberColumn(format="%+d"),
            "均線排列": st.column_config.TextColumn("均線排列", width="small"),
            "MA位置": st.column_config.TextColumn("MA位置", width="small"),
            "扣抵方向": st.column_config.TextColumn("扣抵方向", width="small"),
        },
        disabled=[c for c in show_df.columns if c != "觀察"],
        key="screener_editor",
    )

    # 處理全選加入觀察股
    if add_all_btn:
        all_codes = show_df["代碼"].astype(str).tolist()
        n_existing = len(existing_watchlist)
        merged = list(dict.fromkeys(existing_watchlist + all_codes))
        st.session_state["watchlist_codes"] = merged
        _persist_watchlist(merged)
        added = len(merged) - n_existing
        st.success(f"已全選加入 {added} 檔觀察股（去重後共 {len(merged)} 檔），可至 P-03 盤中雷達載入。")
        if st.button("前往盤中雷達 →", key="goto_radar_all"):
            st.session_state["page"] = "radar"
            st.rerun()

    # 處理勾選加入觀察股
    if add_watchlist_btn:
        selected = edited_df[edited_df["觀察"] == True]  # noqa: E712
        if selected.empty:
            st.warning("請先勾選表格中要加入觀察的股票。")
        else:
            new_codes = selected["代碼"].astype(str).tolist()
            n_existing = len(existing_watchlist)
            merged = list(dict.fromkeys(existing_watchlist + new_codes))
            st.session_state["watchlist_codes"] = merged
            _persist_watchlist(merged)
            added = len(merged) - n_existing
            st.success(f"已加入 {added} 檔觀察股（去重後共 {len(merged)} 檔），可至 P-03 盤中雷達載入。")
            if st.button("前往盤中雷達 →", key="goto_radar_sel"):
                st.session_state["page"] = "radar"
                st.rerun()

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
            st.plotly_chart(fig, width="stretch")

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
            st.plotly_chart(fig2, width="stretch")

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
        st.plotly_chart(fig3, width="stretch")

    # ── 匯出 + LINE 推送 ──
    st.divider()
    col_e1, col_e2, col_e3 = st.columns([2, 1, 1])
    with col_e2:
        csv = display_df.head(top_n).to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 匯出 CSV", csv, "smart_scan_result.csv", "text/csv",
                           width="stretch")
    with col_e3:
        if st.button("📲 推送到 LINE", width="stretch", type="primary"):
            _push_to_line(display_df.head(top_n))


def _push_to_line(df: pd.DataFrame) -> None:
    """將選股結果格式化後推送到 LINE。"""
    from datetime import datetime

    from atlas.constants import TW_TZ
    from atlas.infrastructure.notifications.line import send_line_message_sync

    now = datetime.now(TW_TZ).strftime("%Y/%m/%d %H:%M")
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


# ══════════════════════════════════════════════
# 美股選股
# ══════════════════════════════════════════════

def _render_us_screener() -> None:
    get_colors()

    # ── 圖例說明 ──
    st.markdown("""
    <div class="legend-box">
    <strong>選股邏輯</strong>：掃描美股 Top 股票池 → 技術面評分（動能 + RSI + 均線排列 + MACD + 量比）<br>
    <strong>選股分數</strong>：綜合技術面指標，<span class="legend-good">≥40 強勢推薦</span>、<span class="legend-warn">20~40 值得關注</span>、<span class="legend-bad">&lt;20 偏弱</span><br>
    <strong>RSI(14)</strong>：<span class="legend-bad">&gt;70 超買</span>、50 多空平衡、<span class="legend-good">&lt;30 超賣反彈機會</span><br>
    <strong>均線排列</strong>：<span class="legend-good">多頭排列</span> MA8&gt;MA21&gt;MA55 | <span class="legend-bad">空頭排列</span> MA8&lt;MA21&lt;MA55 | 糾結 其他<br>
    <strong>量比</strong>：當日成交量 / 20日均量，<span class="legend-good">&gt;1.5 放量</span>、<span class="legend-warn">1.0~1.5 正常</span>、<span class="legend-bad">&lt;1.0 縮量</span>
    </div>
    """, unsafe_allow_html=True)

    from atlas.constants_us import US_SECTORS

    # ── 篩選條件 ──
    col1, col2, col3 = st.columns(3)
    with col1:
        sector_filter = st.multiselect("產業篩選", US_SECTORS, default=[])
    with col2:
        sort_by = st.selectbox("排序依據", [
            "綜合分數", "動能(20日)", "RSI", "成交量變化",
        ])
    with col3:
        top_n = st.slider("顯示檔數", 10, 40, 20)

    run_btn = st.button("🔍 開始選股", type="primary", width="stretch")

    # ── 執行掃描 ──
    if run_btn:
        st.session_state["us_scan_result"] = None

    us_result: list[dict] | None = st.session_state.get("us_scan_result")

    if run_btn or us_result is None:
        with st.spinner("掃描美股中，約需 15~60 秒…"):
            try:
                us_result = _scan_us_stocks(sector_filter, sort_by, top_n)
                st.session_state["us_scan_result"] = us_result
            except Exception as exc:
                st.error(f"掃描失敗：{exc}")
                return

    if not us_result:
        st.warning("掃描無結果。請稍後再試或調整篩選條件。")
        return

    _display_us_results(us_result, top_n)


def _scan_us_stocks(
    sector_filter: list[str], sort_by: str, top_n: int
) -> list[dict]:
    """掃描美股，以技術面評分排序。"""
    from atlas.constants_us import US_TOP_STOCKS
    from atlas.presentation.service_container import fetch_us_stock_data, get_indicator_lib

    candidates = US_TOP_STOCKS
    if sector_filter:
        candidates = [(t, n, s) for t, n, s in candidates if s in sector_filter]

    results: list[dict] = []
    lib = get_indicator_lib()

    for ticker, name, sector in candidates:
        try:
            df = fetch_us_stock_data(ticker, "6mo")
            if df is None or df.empty or len(df) < 20:
                continue

            ind = lib.calculate_all(df)
            last = ind.iloc[-1]
            prev = ind.iloc[-2]

            close = float(last["close"])
            change_pct = (close / float(prev["close"]) - 1) * 100

            # 技術面評分
            score = 0
            rsi = float(last.get("RSI14", 50))
            if pd.isna(rsi):
                rsi = 50

            # 動能分（20日）
            mom_20 = (close / float(df["close"].iloc[-20]) - 1) * 100 if len(df) >= 20 else 0.0
            score += min(30, max(-30, int(mom_20 * 3)))

            # RSI 分
            if 40 <= rsi <= 60:
                score += 10
            elif rsi < 30:
                score += 20
            elif rsi > 70:
                score -= 10

            # 均線排列
            ma8 = float(last.get("MA8", 0))
            ma21 = float(last.get("MA21", 0))
            ma55 = float(last.get("MA55", 0))
            if ma8 > ma21 > ma55 > 0:
                score += 20
                ma_text = "多頭排列"
            elif ma8 < ma21 < ma55 and ma55 > 0:
                score -= 10
                ma_text = "空頭排列"
            else:
                ma_text = "糾結"

            # MACD
            macd_hist = float(last.get("MACD_hist", 0))
            if pd.isna(macd_hist):
                macd_hist = 0
            if macd_hist > 0:
                score += 10
            elif macd_hist < 0:
                score -= 5

            # 量能
            vol = float(last["volume"])
            vol_avg = float(df["volume"].iloc[-20:].mean()) if len(df) >= 20 else vol
            vol_ratio = vol / vol_avg if vol_avg > 0 else 1.0

            if vol_ratio > 1.5:
                score += 10

            results.append({
                "代碼": ticker,
                "名稱": name,
                "產業": sector,
                "收盤": round(close, 2),
                "漲跌%": round(change_pct, 2),
                "選股分數": score,
                "RSI": round(rsi, 1),
                "20日動能%": round(mom_20, 2),
                "均線排列": ma_text,
                "量比": round(vol_ratio, 2),
                "MACD": round(macd_hist, 3),
            })
        except Exception:
            continue

    # 排序
    if sort_by == "動能(20日)":
        results.sort(key=lambda x: x["20日動能%"], reverse=True)
    elif sort_by == "RSI":
        results.sort(key=lambda x: abs(x["RSI"] - 50))
    elif sort_by == "成交量變化":
        results.sort(key=lambda x: x["量比"], reverse=True)
    else:
        results.sort(key=lambda x: x["選股分數"], reverse=True)

    return results[:top_n]


def _display_us_results(results: list[dict], top_n: int) -> None:
    """顯示美股選股結果：統計卡片 + 表格 + 圖表 + 觀察股。"""

    result_df = pd.DataFrame(results)

    # ── 統計卡片 ──
    st.divider()
    st.subheader("掃描結果統計")
    total = len(result_df)
    bull_count = len(result_df[result_df["均線排列"] == "多頭排列"])
    high_mom = len(result_df[result_df["20日動能%"] > 5])
    high_vol = len(result_df[result_df["量比"] > 1.5])
    high_score = len(result_df[result_df["選股分數"] >= 40])

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(metric_card("掃描命中", str(total), status="positive"),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("多頭排列", str(bull_count),
                    status="positive" if bull_count > 0 else "neutral"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("強動能(>5%)", str(high_mom), status="positive"),
                    unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("放量(>1.5)", str(high_vol), status="positive"),
                    unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card("高分(>=40)", str(high_score),
                    status="positive" if high_score > 0 else "neutral"),
                    unsafe_allow_html=True)

    # ── 結果表格 ──
    st.divider()
    st.subheader(f"美股選股清單（共 {total} 檔）")

    # ── 觀察股操作區 ──
    existing_watchlist: list[str] = st.session_state.get("watchlist_codes", [])
    col_w0, col_w1, col_w2, col_w3, col_w4 = st.columns([0.5, 1, 1, 1, 2])
    with col_w0:
        select_all = st.checkbox("全選", key="us_screener_select_all")
    with col_w1:
        add_watchlist_btn = st.button("⭐ 加入觀察股", type="primary",
                                      width="stretch", key="us_add_watch")
    with col_w2:
        add_all_btn = st.button("⭐ 全選加入觀察股", width="stretch",
                                key="us_add_all_watch")
    with col_w3:
        if existing_watchlist and st.button("🗑 清空觀察股", width="stretch",
                                            key="us_clear_watch"):
            st.session_state["watchlist_codes"] = []
            _persist_watchlist([])
            st.rerun()
    with col_w4:
        if existing_watchlist:
            st.info(
                f"觀察股 {len(existing_watchlist)} 檔："
                f"{', '.join(existing_watchlist[:10])}"
                f"{'…' if len(existing_watchlist) > 10 else ''}"
            )
        else:
            st.caption("勾選下方表格左側「觀察」欄，再點加入觀察股。")

    show_df = result_df.copy()
    show_df.insert(0, "觀察", select_all)

    edited_df = st.data_editor(
        show_df,
        width="stretch",
        hide_index=True,
        height=min(600, 40 + len(show_df) * 35),
        column_config={
            "觀察": st.column_config.CheckboxColumn("觀察", default=False, width="small"),
            "選股分數": st.column_config.ProgressColumn(min_value=-50, max_value=100, format="%.0f"),
            "RSI": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
            "漲跌%": st.column_config.NumberColumn(format="%+.2f%%"),
            "收盤": st.column_config.NumberColumn(format="$%.2f"),
            "20日動能%": st.column_config.NumberColumn(format="%+.2f%%"),
            "量比": st.column_config.NumberColumn(format="%.2f"),
            "MACD": st.column_config.NumberColumn(format="%.3f"),
        },
        disabled=[c for c in show_df.columns if c != "觀察"],
        key="us_screener_editor",
    )

    # 處理全選加入觀察股
    if add_all_btn:
        all_codes = show_df["代碼"].astype(str).tolist()
        n_existing = len(existing_watchlist)
        merged = list(dict.fromkeys(existing_watchlist + all_codes))
        st.session_state["watchlist_codes"] = merged
        _persist_watchlist(merged)
        added = len(merged) - n_existing
        st.success(f"已全選加入 {added} 檔觀察股（去重後共 {len(merged)} 檔）。")

    # 處理勾選加入觀察股
    if add_watchlist_btn:
        selected = edited_df[edited_df["觀察"] == True]  # noqa: E712
        if selected.empty:
            st.warning("請先勾選表格中要加入觀察的股票。")
        else:
            new_codes = selected["代碼"].astype(str).tolist()
            n_existing = len(existing_watchlist)
            merged = list(dict.fromkeys(existing_watchlist + new_codes))
            st.session_state["watchlist_codes"] = merged
            _persist_watchlist(merged)
            added = len(merged) - n_existing
            st.success(f"已加入 {added} 檔觀察股（去重後共 {len(merged)} 檔）。")

    # ── 圖表區 ──
    st.divider()
    col_a, col_b = st.columns(2)

    top10 = result_df.head(10)

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
            st.plotly_chart(fig, width="stretch")

    with col_b:
        st.subheader("20日動能 — Top 10")
        if not top10.empty:
            labels = [f"{r['代碼']}\n{r['名稱']}" for _, r in top10.iterrows()]
            mom_vals = top10["20日動能%"].tolist()
            colors = ["#4caf50" if v >= 0 else "#f44336" for v in mom_vals]

            fig2 = go.Figure(go.Bar(
                x=labels, y=mom_vals,
                marker_color=colors,
                text=[f"{v:+.1f}%" for v in mom_vals],
                textposition="outside",
            ))
            fig2.update_layout(
                title="20日動能排行 (%)",
                height=350,
                margin=dict(l=0, r=0, t=40, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e0e0e0"),
            )
            fig2.add_hline(y=0, line_color="#555")
            st.plotly_chart(fig2, width="stretch")

    # ── 產業分佈 ──
    st.divider()
    st.subheader("產業分佈")
    sector_counts: dict[str, int] = {}
    for r in results:
        s = r["產業"]
        sector_counts[s] = sector_counts.get(s, 0) + 1

    if sector_counts:
        sorted_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
        s_names = [x[0] for x in sorted_sectors]
        s_counts = [x[1] for x in sorted_sectors]

        fig3 = go.Figure(go.Bar(
            x=s_names, y=s_counts,
            marker_color="#42a5f5",
            text=[str(c) for c in s_counts],
            textposition="outside",
        ))
        fig3.update_layout(
            title="各產業命中數",
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e0e0e0"),
            xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig3, width="stretch")

    # ── 匯出 ──
    st.divider()
    col_e1, col_e2 = st.columns([3, 1])
    with col_e2:
        csv = result_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 匯出 CSV", csv, "us_scan_result.csv", "text/csv",
                           width="stretch")
