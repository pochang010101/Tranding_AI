"""P-04 每日選股 — 四主軸+三面向明細、精選清單、產業分佈。"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.components.charts import bar_chart, heatmap


def render() -> None:
    st.title("🔍 每日選股")
    market = st.session_state.get("market", "TW")
    c = get_colors()

    # ── 控制列 ──────────────────────────────────
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        scan_date = st.date_input("掃描日期", value=None)
    with col2:
        top_n = st.selectbox("顯示筆數", [10, 20, 30, 50], index=1)
    with col3:
        min_level = st.selectbox("最低等級", ["Lv5", "Lv4", "Lv3", "Lv2", "Lv1", "全部"], index=2)

    if st.button("🔍 執行掃描", type="primary", use_container_width=True):
        with st.spinner("正在掃描全市場..."):
            st.session_state["scan_running"] = True

    # ── 掃描統計 ────────────────────────────────
    st.divider()
    st.subheader("掃描結果統計")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card("掃描標的", "1,856", status="neutral"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("通過篩選", "127", status="positive"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("Lv3 以上", "38", status="positive"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("精選推薦", "12", status="positive"), unsafe_allow_html=True)

    # ── 精選清單表格 ────────────────────────────
    st.divider()
    st.subheader("精選清單")

    demo_data = pd.DataFrame({
        "排名": range(1, 11),
        "代碼": ["2330", "2454", "3008", "6547", "2881", "2317", "2382", "3711", "2603", "2886"],
        "名稱": ["台積電", "聯發科", "大立光", "高端疫苗", "富邦金", "鴻海", "廣達", "日月光", "長榮", "兆豐金"],
        "主軸總分": [85.2, 78.6, 75.3, 72.1, 70.8, 68.5, 67.2, 65.9, 64.3, 62.1],
        "產業RS": [88, 82, 75, 68, 72, 65, 78, 70, 55, 60],
        "資金流": [90, 85, 78, 75, 68, 72, 62, 65, 70, 58],
        "個股RS": [82, 72, 73, 74, 72, 68, 62, 63, 68, 68],
        "技術面": ["🟢", "🟢", "🟢", "🟢", "⚪", "🟢", "🟢", "⚪", "🟢", "⚪"],
        "基本面": ["🟢", "🟢", "🟢", "⚪", "🟢", "⚪", "🟢", "🟢", "⚪", "🟢"],
        "籌碼面": ["🟢", "🟢", "⚪", "🟢", "🟢", "🟢", "⚪", "🟢", "🟢", "⚪"],
        "結論": ["Lv5", "Lv4", "Lv4", "Lv3", "Lv3", "Lv3", "Lv3", "Lv3", "Lv3", "Lv2"],
    })

    # 篩選
    if min_level != "全部":
        level_order = {"Lv5": 5, "Lv4": 4, "Lv3": 3, "Lv2": 2, "Lv1": 1}
        min_val = level_order.get(min_level, 0)
        demo_data = demo_data[demo_data["結論"].map(lambda x: level_order.get(x, 0) >= min_val)]

    st.dataframe(
        demo_data.head(top_n),
        use_container_width=True,
        hide_index=True,
        column_config={
            "主軸總分": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
            "產業RS": st.column_config.ProgressColumn(min_value=0, max_value=100),
            "資金流": st.column_config.ProgressColumn(min_value=0, max_value=100),
            "個股RS": st.column_config.ProgressColumn(min_value=0, max_value=100),
        },
    )

    # ── 四主軸分數分佈 ─────────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("四主軸分數 — Top 5")
        fig = bar_chart(
            labels=demo_data["名稱"].head(5).tolist(),
            values=demo_data["主軸總分"].head(5).tolist(),
            title="主軸總分排行",
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("產業分佈")
        industries = ["半導體", "金融", "光電", "航運", "生技"]
        counts = [4, 2, 2, 1, 1]
        fig = bar_chart(
            labels=industries, values=counts,
            title="精選清單產業分佈",
            horizontal=True, height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── 匯出按鈕 ────────────────────────────────
    st.divider()
    col_e1, col_e2 = st.columns([3, 1])
    with col_e2:
        csv = demo_data.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 匯出 CSV", csv, "scan_result.csv", "text/csv",
                          use_container_width=True)
