"""P-04 每日選股 — 全市場智慧篩選：法人買賣、量能、價格動能。"""

from __future__ import annotations

import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from atlas.presentation.components.charts import bar_chart
from atlas.presentation.components.theme import get_colors, metric_card

logger = logging.getLogger(__name__)


def _run_smart_scan() -> pd.DataFrame:
    """執行全市場智慧掃描（快取 10 分鐘）。"""
    from atlas.application.smart_screener import SmartScreener

    screener = SmartScreener(
        min_price=st.session_state.get("scr_min_price", 10.0),
        min_volume_lots=st.session_state.get("scr_min_vol", 500),
    )
    return screener.scan_to_dataframe()


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
    <span class="legend-warn">漲停</span> 漲幅≥9.5%<br>
    <strong>選股分數</strong>：分數越高表示多個正面訊號同時出現，<span class="legend-good">≥50 強烈推薦</span>、<span class="legend-warn">30~50 值得關注</span>、<span class="legend-bad">&lt;30 單一訊號</span>
    </div>
    """, unsafe_allow_html=True)

    # ── 控制列 ──
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        min_price = st.number_input("最低股價", value=10.0, step=5.0, key="scr_min_price")
    with col2:
        min_vol = st.number_input("最低成交量(張)", value=500, step=100, key="scr_min_vol")
    with col3:
        top_n = st.selectbox("顯示筆數", [20, 50, 100, 200], index=1)
    with col4:
        tag_filter = st.multiselect(
            "篩選標籤",
            ["外資買超", "投信買超", "雙法人", "外資大買", "投信大買", "大量", "爆量", "強勢", "漲停"],
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
                scan_result = _run_smart_scan()
                st.session_state["smart_scan_result"] = scan_result
            except Exception as exc:
                st.error(f"掃描失敗：{exc}")
                st.info("可能原因：非交易時段、API 暫時無法連線。請稍後再試。")
                return

    if scan_result is None or scan_result.empty:
        st.warning("掃描無結果。可能原因：非交易日、API 尚未更新、或篩選條件過嚴。")
        return

    # ── 標籤篩選 ──
    display_df = scan_result.copy()
    if tag_filter:
        mask = display_df["訊號標籤"].apply(
            lambda tags: any(t in tags for t in tag_filter)
        )
        display_df = display_df[mask]

    if display_df.empty:
        st.warning("沒有符合所選標籤的結果。")
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

    # ── 匯出 ──
    st.divider()
    col_e1, col_e2 = st.columns([3, 1])
    with col_e2:
        csv = display_df.head(top_n).to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 匯出 CSV", csv, "smart_scan_result.csv", "text/csv",
                           use_container_width=True)
