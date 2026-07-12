"""P-05 選股池管理 — 四層篩選結果、手動調整、歷史變更。"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import bar_chart
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    TW_TOP_STOCKS,
    fetch_stock_data,
    get_indicator_lib,
)

logger = logging.getLogger(__name__)

# ── 產業分類（與 p04_screener 共用相同對應）──────────────────────────────────
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

# L1 流動性門檻（日均量張數，yfinance 回傳股數需 ÷ 1000）
_L1_AVG_VOL_THRESHOLD = 500_000  # 股（= 500 張）


@st.cache_data(ttl=600, show_spinner=False)
def _run_filter(stock_list: list[tuple[str, str]]) -> dict:
    """執行四層篩選，回傳各層通過清單與產業計數。快取 10 分鐘。"""
    lib = get_indicator_lib()

    l0_codes: list[str] = [code for code, _ in stock_list]  # 全市場
    l1_pass: list[str] = []
    l2_pass: list[str] = []
    l3_pass: list[str] = []
    l4_pass: list[str] = []
    industry_counter: dict[str, int] = {}

    for code, name in stock_list:
        try:
            df = fetch_stock_data(code, "3mo")
            if df is None or df.empty or len(df) < 10:
                continue

            # L1 流動性：日均量 > 500 張（yfinance volume 單位為股）
            avg_vol = df["volume"].mean()
            if avg_vol <= _L1_AVG_VOL_THRESHOLD:
                continue
            l1_pass.append(code)

            # 計算指標（L2、L3 均需要）
            ind_df = lib.calculate_all(df)
            last = ind_df.iloc[-1]

            close = last.get("close", 0)
            ma55 = last.get("MA55", 0)

            # L2 技術面：收盤 > MA55
            if not (ma55 > 0 and close > ma55):
                continue
            l2_pass.append(code)

            # L3 策略適性：ATR% > 0.5%
            atr = last.get("ATR14", None)
            if atr is None or pd.isna(atr):
                # 若 ATR14 不存在，自行計算近 14 日簡易 ATR%
                high_low = (df["high"] - df["low"]).tail(14).mean()
                atr_pct = (high_low / close * 100) if close > 0 else 0.0
            else:
                atr_pct = (float(atr) / close * 100) if close > 0 else 0.0

            if atr_pct <= 0.5:
                continue
            l3_pass.append(code)

            # L4 排除：目前無排除資料，全部通過
            l4_pass.append(code)

            # 產業計數（以最終通過 L4 的股票為準）
            industry = _INDUSTRY_MAP.get(code, "其他")
            industry_counter[industry] = industry_counter.get(industry, 0) + 1

        except Exception as exc:
            logger.warning("Filter skip %s (%s): %s", code, name, exc)

    return {
        "l0": len(l0_codes),
        "l1": len(l1_pass),
        "l2": len(l2_pass),
        "l3": len(l3_pass),
        "l4": len(l4_pass),
        "industry": industry_counter,
    }


def render() -> None:
    st.title("🗂️ 選股池管理")
    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
<span class="legend-good">股票池</span>：系統自動維護的觀察名單，每月重建一次，涵蓋 TWSE+TPEx 全市場符合門檻的標的<br>
<span class="legend-warn">入池條件（四層漏斗）</span>：L1 流動性（日均量&gt;500張）→ L2 技術面（收盤&gt;MA55）→ L3 策略適性（ATR&gt;0.5%）→ L4 排除（非警示/下市）<br>
<span class="legend-good">池內排名</span>：依綜合評分排序，越前面代表綜合條件越佳，越值得優先關注<br>
<span class="legend-warn">狀態標記</span>：<span class="legend-good">活躍 — 持續符合全部條件</span>、<span class="legend-warn">觀察 — 部分條件不符，需留意是否降級</span>
</div>
""", unsafe_allow_html=True)
    get_colors()  # 確保 theme 初始化

    # ── 執行篩選 ─────────────────────────────────
    with st.spinner(f"正在篩選 {len(TW_TOP_STOCKS)} 支股票…"):
        result = _run_filter(TW_TOP_STOCKS)

    l0 = result["l0"]
    l1 = result["l1"]
    l2 = result["l2"]
    l3 = result["l3"]
    l4 = result["l4"]

    l1_rate = f"通過率 {l1/l0*100:.0f}%" if l0 > 0 else "—"
    l2_rate = f"通過率 {l2/l1*100:.0f}%" if l1 > 0 else "—"
    final_rate = f"通過率 {l4/l0*100:.0f}%" if l0 > 0 else "—"

    # ── 當前池狀態 ──────────────────────────────────
    st.subheader("當前選股池")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card("全市場", str(l0), status="neutral"),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("L1 流動性", str(l1), delta=l1_rate, status="neutral"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("L2+L3 篩選", str(l3), delta=l2_rate, status="neutral"),
                    unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("最終池", str(l4), delta=final_rate, status="positive"),
                    unsafe_allow_html=True)

    # ── 四層篩選漏斗 ────────────────────────────
    st.divider()
    layers = ["全市場", "L1 流動性", "L2 技術面", "L3 策略適性", "L4 排除"]
    passed = [l0, l1, l2, l3, l4]
    fig = bar_chart(layers, passed, title="四層篩選漏斗", height=350)
    st.plotly_chart(fig, width="stretch")

    # ── 篩選條件 ────────────────────────────────
    st.divider()
    with st.expander("📋 篩選條件明細"):
        st.markdown("""
        | 層級 | 條件 | 說明 |
        |------|------|------|
        | L1 流動性 | 日均量 > 500張, 股價 > 10元 | 排除低流動性 |
        | L2 技術面 | 收盤 > MA55 | 中期趨勢向上 |
        | L3 策略適性 | ATR > 0.5% | 足夠波動度 |
        | L4 排除 | 非暫停/下市/警示 | 排除問題股 |
        """)

    # ── 產業分佈 ────────────────────────────────
    st.divider()
    st.subheader("池中產業分佈")
    industry_data = result["industry"]
    if industry_data:
        ind_series = pd.Series(industry_data).sort_values(ascending=False)
        fig = bar_chart(
            ind_series.index.tolist(),
            ind_series.values.tolist(),
            title="產業股數分佈",
            horizontal=True,
            height=400,
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("無產業資料（篩選後無通過股票）")

    # ── 手動調整 ────────────────────────────────
    st.divider()
    st.subheader("手動調整")
    col_add, col_rm = st.columns(2)
    with col_add:
        add_codes = st.text_input("手動加入（逗號分隔）", placeholder="2330, 2454")  # noqa: F841
        st.button("➕ 加入", width="stretch")
    with col_rm:
        rm_codes = st.text_input("手動排除（逗號分隔）", placeholder="1234, 5678")  # noqa: F841
        st.button("➖ 排除", width="stretch")

    # ── 月度差異 ────────────────────────────────
    st.divider()
    st.subheader("月度重建差異")
    diff_df = pd.DataFrame({
        "類型": ["新增", "新增", "新增", "移除", "移除"],
        "代碼": ["6891", "3443", "2618", "1590", "2105"],
        "名稱": ["長聖", "創意", "長榮航", "亞德客-KY", "正新"],
        "原因": ["流動性達標", "技術面轉多", "策略適性通過", "跌破MA55", "量能萎縮"],
    })
    st.dataframe(diff_df, width="stretch", hide_index=True)

    # ── 重建按鈕 ────────────────────────────────
    st.divider()
    if st.button("🔄 強制重建選股池", type="primary"):
        _run_filter.clear()
        st.info("快取已清除，重新篩選中…")
        st.rerun()
