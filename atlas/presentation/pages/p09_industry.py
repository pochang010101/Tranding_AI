"""P-09 產業分析 — RS 熱力圖、族群資金流、輪動趨勢。"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.components.charts import bar_chart, heatmap


def render() -> None:
    st.title("🏭 產業分析")
    c = get_colors()

    # ── 產業 RS 排行 ────────────────────────────
    st.subheader("產業相對強度排行")

    rs_df = pd.DataFrame({
        "排名": range(1, 11),
        "產業": ["半導體", "AI/雲端", "電動車", "金融", "光電",
                 "生技", "航運", "鋼鐵", "傳產", "營建"],
        "RS_5d": [8.5, 6.2, 4.8, 2.1, 1.5, -0.3, -1.2, -2.5, -3.1, -4.2],
        "RS_20d": [12.3, 9.5, 7.2, 3.8, 2.1, 1.5, -0.5, -3.8, -5.2, -6.1],
        "RS_60d": [25.6, 18.2, 15.3, 5.2, 3.8, 2.1, -2.5, -8.5, -10.2, -12.5],
        "5日排名": [1, 2, 3, 5, 4, 7, 6, 8, 9, 10],
        "20日排名": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "趨勢": ["🔥 領漲", "🔥 領漲", "⬆️ 上升", "➡️ 持平", "⬇️ 下降",
                 "⬇️ 下降", "⬇️ 下降", "❄️ 落後", "❄️ 落後", "❄️ 落後"],
    })
    st.dataframe(rs_df, use_container_width=True, hide_index=True,
                 column_config={
                     "RS_5d": st.column_config.NumberColumn(format="%+.1f%%"),
                     "RS_20d": st.column_config.NumberColumn(format="%+.1f%%"),
                     "RS_60d": st.column_config.NumberColumn(format="%+.1f%%"),
                 })

    # ── RS 柱狀圖 ──────────────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("20日 RS 排行")
        fig = bar_chart(
            rs_df["產業"].tolist(),
            rs_df["RS_20d"].tolist(),
            title="20日相對強度 %",
            horizontal=True, color_by_value=True, height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("產業輪動偵測")
        rotation_df = pd.DataFrame({
            "產業": ["光電", "金融", "航運"],
            "趨勢": ["RISING", "RISING", "FALLING"],
            "5日排名": [4, 5, 6],
            "20日排名": [5, 4, 7],
            "排名變化": [+3, +2, -3],
        })
        st.dataframe(rotation_df, use_container_width=True, hide_index=True,
                     column_config={
                         "排名變化": st.column_config.NumberColumn(format="%+d"),
                     })

    # ── 族群資金流向 ────────────────────────────
    st.divider()
    st.subheader("族群資金淨流入（5日）")

    flow_industries = ["半導體", "AI/雲端", "金融", "電動車", "光電",
                       "生技", "航運", "鋼鐵", "傳產", "營建"]
    flow_values = [850, 520, 280, 180, -50, -120, -280, -350, -420, -510]
    fig = bar_chart(
        flow_industries, flow_values,
        title="5日淨流入（百萬）",
        horizontal=True, color_by_value=True, height=450,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 產業集中度 ──────────────────────────────
    st.divider()
    st.subheader("選股池產業集中度")
    st.warning("⚠️ 半導體佔比 18.2%，接近上限 20%。建議分散至其他族群。")
