"""P-09 產業分析 — RS 熱力圖、族群資金流、輪動趨勢。"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.components.charts import bar_chart, heatmap  # noqa: F401
from atlas.presentation.service_container import (
    TW_TOP_STOCKS,
    fetch_stock_data,
    get_indicator_lib,
)

logger = logging.getLogger(__name__)

_INDUSTRY_MAP: dict[str, str] = {
    "2330": "半導體", "2454": "半導體", "2303": "半導體", "3711": "半導體",
    "3008": "光電", "2395": "科技",
    "2317": "電子製造", "2382": "電子製造", "2357": "電子製造",
    "2308": "電子零件",
    "2881": "金融", "2882": "金融", "2891": "金融", "2886": "金融",
    "2884": "金融", "2892": "金融", "5880": "金融", "2880": "金融", "2885": "金融",
    "2412": "電信", "3045": "電信", "4904": "電信",
    "1301": "石化", "1303": "石化", "6505": "石化",
    "2002": "鋼鐵", "2603": "航運",
    "1216": "食品", "2912": "食品", "2207": "汽車",
}


@st.cache_data(ttl=600, show_spinner=False)
def _calc_industry_rs(stock_list: list[tuple[str, str]]) -> pd.DataFrame:
    """計算各產業 RS（5/20/60 日均漲幅）及資金流代理指標。"""
    rows = []

    for code, name in stock_list:
        try:
            df = fetch_stock_data(code, "3mo")
            if df is None or df.empty or len(df) < 10:
                continue

            close = df["close"]
            volume = df["volume"] if "volume" in df.columns else pd.Series(dtype=float)

            def _ret(n: int) -> float:
                if len(close) < n + 1:
                    return float("nan")
                return float((close.iloc[-1] - close.iloc[-n - 1]) / close.iloc[-n - 1] * 100)

            # 資金流代理：最近 5 日每日 (price_change_direction * volume) 累加
            proxy_flow = 0.0
            if not volume.empty and len(close) >= 6:
                for i in range(-5, 0):
                    direction = 1 if close.iloc[i] >= close.iloc[i - 1] else -1
                    proxy_flow += direction * float(volume.iloc[i]) * float(close.iloc[i])
            # 換算百萬
            proxy_flow_m = proxy_flow / 1_000_000

            rows.append({
                "代碼": code,
                "名稱": name,
                "產業": _INDUSTRY_MAP.get(code, "其他"),
                "RS_5d": _ret(5),
                "RS_20d": _ret(20),
                "RS_60d": _ret(min(60, len(close) - 1)),
                "flow_proxy_m": proxy_flow_m,
            })
        except Exception as exc:
            logger.warning("Skip %s: %s", code, exc)

    if not rows:
        return pd.DataFrame()

    stock_df = pd.DataFrame(rows)

    # 產業聚合：平均 RS + 加總資金流代理
    grouped = stock_df.groupby("產業", sort=False).agg(
        RS_5d=("RS_5d", "mean"),
        RS_20d=("RS_20d", "mean"),
        RS_60d=("RS_60d", "mean"),
        flow_proxy_m=("flow_proxy_m", "sum"),
        股票數=("代碼", "count"),
    ).reset_index()

    grouped = grouped.dropna(subset=["RS_20d"])
    grouped = grouped.sort_values("RS_20d", ascending=False).reset_index(drop=True)

    return grouped, stock_df  # type: ignore[return-value]


def render() -> None:
    st.title("🏭 產業分析")
    get_colors()

    with st.spinner(f"正在計算 {len(TW_TOP_STOCKS)} 支股票產業 RS，請稍候…"):
        result = _calc_industry_rs(TW_TOP_STOCKS)

    if result is None or (isinstance(result, tuple) and result[0].empty):
        st.warning("無法取得資料，請檢查網路連線或稍後再試。")
        return

    grouped, stock_df = result

    # ── 產業 RS 排行 ────────────────────────────
    st.subheader("產業相對強度排行")

    # 以 RS_20d 排名決定 rank，再比 RS_5d 排名判定趨勢
    grouped = grouped.reset_index(drop=True)
    grouped["20日排名"] = grouped["RS_20d"].rank(ascending=False, method="min").astype(int)
    grouped["5日排名"] = grouped["RS_5d"].rank(ascending=False, method="min").astype(int)
    grouped["排名變化"] = grouped["20日排名"] - grouped["5日排名"]  # 正 = 5日比20日排名更高 → 上升動能

    def _trend(row: pd.Series) -> str:
        chg = row["排名變化"]
        rs20 = row["RS_20d"]
        if rs20 >= 5 and chg >= 2:
            return "🔥 領漲"
        elif chg >= 1:
            return "⬆️ 上升"
        elif chg <= -2:
            return "❄️ 落後"
        elif chg <= -1:
            return "⬇️ 下降"
        else:
            return "➡️ 持平"

    grouped["趨勢"] = grouped.apply(_trend, axis=1)
    grouped.insert(0, "排名", range(1, len(grouped) + 1))

    display_rs = grouped[["排名", "產業", "RS_5d", "RS_20d", "RS_60d", "5日排名", "20日排名", "趨勢"]].copy()
    st.dataframe(
        display_rs,
        width="stretch",
        hide_index=True,
        column_config={
            "RS_5d":  st.column_config.NumberColumn("RS 5日%",  format="%+.2f%%"),
            "RS_20d": st.column_config.NumberColumn("RS 20日%", format="%+.2f%%"),
            "RS_60d": st.column_config.NumberColumn("RS 60日%", format="%+.2f%%"),
        },
    )

    # ── RS 柱狀圖 ──────────────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("20日 RS 排行")
        fig = bar_chart(
            grouped["產業"].tolist(),
            grouped["RS_20d"].round(2).tolist(),
            title="20日相對強度 %",
            horizontal=True, color_by_value=True, height=400,
        )
        st.plotly_chart(fig, width="stretch")

    with col_b:
        st.subheader("產業輪動偵測")
        # 只顯示有明顯動向的產業（排名變化 != 0）
        rotation_df = grouped[grouped["排名變化"] != 0][
            ["產業", "趨勢", "5日排名", "20日排名", "排名變化"]
        ].copy()
        if rotation_df.empty:
            st.info("各產業排名無明顯變化")
        else:
            rotation_df = rotation_df.sort_values("排名變化", ascending=False).reset_index(drop=True)
            st.dataframe(
                rotation_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "排名變化": st.column_config.NumberColumn(format="%+d"),
                },
            )

    # ── 族群資金流向（代理指標） ───────────────
    st.divider()
    st.subheader("族群資金淨流入代理（5日，百萬）")
    st.caption("以 Σ(漲跌方向 × 成交量 × 收盤價) 估算，正值代表資金淨流入")

    flow_sorted = grouped.sort_values("flow_proxy_m", ascending=False)
    fig = bar_chart(
        flow_sorted["產業"].tolist(),
        flow_sorted["flow_proxy_m"].round(1).tolist(),
        title="5日資金流代理（百萬）",
        horizontal=True, color_by_value=True, height=450,
    )
    st.plotly_chart(fig, width="stretch")

    # ── 產業集中度 ──────────────────────────────
    st.divider()
    st.subheader("選股池產業集中度")

    total_stocks = len(stock_df)
    industry_counts = stock_df["產業"].value_counts().reset_index()
    industry_counts.columns = ["產業", "股票數"]
    industry_counts["佔比%"] = (industry_counts["股票數"] / total_stocks * 100).round(1)

    col_c, col_d = st.columns(2)

    with col_c:
        st.dataframe(industry_counts, width="stretch", hide_index=True,
                     column_config={
                         "佔比%": st.column_config.NumberColumn(format="%.1f%%"),
                     })

    with col_d:
        fig_conc = bar_chart(
            industry_counts["產業"].tolist(),
            industry_counts["佔比%"].tolist(),
            title="產業佔比（%）",
            horizontal=True, height=350,
        )
        st.plotly_chart(fig_conc, width="stretch")

    # 集中度警示（超過 20%）
    over_limit = industry_counts[industry_counts["佔比%"] >= 20]
    if not over_limit.empty:
        for _, row in over_limit.iterrows():
            st.warning(
                f"⚠️ {row['產業']} 佔比 {row['佔比%']:.1f}%，接近或超過上限 20%。建議分散至其他族群。"
            )
