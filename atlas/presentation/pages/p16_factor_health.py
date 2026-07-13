"""P-16 因子健檢 — 因子 ICIR 排名 + 策略健康度日報。"""

from __future__ import annotations

import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from atlas.presentation.components.charts import _apply_layout
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    get_daily_backtest_engine,
    get_factor_mining_engine,
)

logger = logging.getLogger(__name__)


def _render_factor_section() -> None:
    """因子探勘結果展示。"""
    st.subheader("因子 IC/ICIR 排名")
    c = get_colors()

    st.caption("因子探勘需要歷史因子值和報酬資料。以下為模擬展示。")

    st.markdown("""
    <div class="legend-box">
    <strong>指標說明</strong><br>
    <span class="legend-good">IC均值</span>：因子與未來報酬的相關性，<span class="legend-good">≥0.03 有預測力</span>、<span class="legend-bad">&lt;0.03 無效</span><br>
    <span class="legend-good">ICIR</span>：IC均值/IC標準差，衡量因子穩定性，<span class="legend-good">≥0.5 穩定有效</span>、<span class="legend-warn">0~0.5 不穩定</span>、<span class="legend-bad">&lt;0 反向</span><br>
    ✅ = IC≥0.03 且 ICIR≥0.5（穩定有效因子）&nbsp; ❌ = 不符合條件
    </div>
    """, unsafe_allow_html=True)

    # 模擬因子資料（實際接入後替換為真實計算）
    import numpy as np
    get_factor_mining_engine()

    np.random.seed(42)
    factor_names = [
        "RSI_14", "MACD_hist", "MA_alignment", "Volume_ratio",
        "Fund_flow", "RS_20d", "KD_cross", "OBV_slope",
        "Chip_concentration", "Industry_rotation",
    ]

    demo_stats = []
    for name in factor_names:
        ic_mean = np.random.uniform(-0.05, 0.15)
        ic_std = np.random.uniform(0.03, 0.08)
        icir = ic_mean / ic_std if ic_std > 0 else 0
        demo_stats.append({
            "因子": name,
            "IC均值": round(ic_mean, 4),
            "IC標準差": round(ic_std, 4),
            "ICIR": round(icir, 2),
            "有效": "✅" if abs(ic_mean) >= 0.03 and abs(icir) >= 0.5 else "❌",
        })

    demo_df = pd.DataFrame(demo_stats).sort_values("ICIR", ascending=False)
    demo_df.insert(0, "排名", range(1, len(demo_df) + 1))

    # ICIR 柱狀圖
    fig = go.Figure(go.Bar(
        x=demo_df["因子"].tolist(),
        y=demo_df["ICIR"].tolist(),
        marker_color=[
            c["positive"] if v >= 0.5 else c["warning"] if v >= 0 else c["negative"]
            for v in demo_df["ICIR"]
        ],
        text=[f"{v:.2f}" for v in demo_df["ICIR"]],
        textposition="outside",
    ))
    fig = _apply_layout(fig, "因子 ICIR 排名", 350)
    fig.update_layout(
        xaxis=dict(tickangle=-45),
        yaxis=dict(title="ICIR"),
    )
    fig.add_hline(y=0.5, line_dash="dash", line_color="#4caf50",
                  annotation_text="有效閾值 (0.5)")
    fig.add_hline(y=0, line_dash="solid", line_color="#666")
    st.plotly_chart(fig, width="stretch")

    # 明細表
    st.dataframe(
        demo_df,
        hide_index=True,
        width="stretch",
        column_config={
            "ICIR": st.column_config.NumberColumn(format="%.2f"),
            "IC均值": st.column_config.NumberColumn(format="%.4f"),
            "IC標準差": st.column_config.NumberColumn(format="%.4f"),
        },
    )

    valid_count = len([s for s in demo_stats if "✅" in s["有效"]])
    st.caption(f"有效因子: {valid_count}/{len(demo_stats)} | "
               f"ICIR 閾值: 0.5 | IC 閾值: 0.03")


def _render_strategy_health() -> None:
    """策略健康度日報。"""
    st.subheader("策略健康度日報")
    c = get_colors()

    engine = get_daily_backtest_engine()

    st.markdown("""
    <div class="legend-box">
    <strong>指標說明</strong><br>
    <span class="legend-good">健康分</span>：0~100 綜合評分，<span class="legend-good">≥60 健康</span>、<span class="legend-warn">40~60 需關注</span>、<span class="legend-bad">&lt;40 異常</span><br>
    <span class="legend-good">勝率</span>：獲利交易佔比，<span class="legend-good">≥50% 正常</span>、<span class="legend-bad">&lt;40% 偏低</span><br>
    <span class="legend-good">均報酬%</span>：每筆交易平均損益，<span class="legend-good">&gt;0 獲利</span>、<span class="legend-bad">&lt;0 虧損</span><br>
    <span class="legend-good">權重調整</span>：系統建議的倉位調整係數，<span class="legend-good">&gt;1 可加碼</span>、<span class="legend-bad">&lt;1 應減碼</span>
    </div>
    """, unsafe_allow_html=True)

    # 模擬策略交易資料（實際接入後替換）
    import numpy as np
    np.random.seed(42)

    strategies = {
        "MA_crossover": [
            {"return_pct": r, "is_win": r > 0}
            for r in np.random.normal(1.5, 3, 15).tolist()
        ],
        "RSI_oversold": [
            {"return_pct": r, "is_win": r > 0}
            for r in np.random.normal(0.8, 4, 10).tolist()
        ],
        "MACD_divergence": [
            {"return_pct": r, "is_win": r > 0}
            for r in np.random.normal(2.0, 2.5, 12).tolist()
        ],
        "Granville_B1": [
            {"return_pct": r, "is_win": r > 0}
            for r in np.random.normal(-0.5, 5, 8).tolist()
        ],
        "Breakout_volume": [
            {"return_pct": r, "is_win": r > 0}
            for r in np.random.normal(1.2, 3.5, 20).tolist()
        ],
    }

    report = engine.run_daily_check(strategies)

    # 概覽卡片
    cols = st.columns(4)
    with cols[0]:
        st.markdown(metric_card(
            "策略數", str(len(report.strategies)), status="neutral",
        ), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(metric_card(
            "健康", str(report.healthy_count),
            status="positive" if report.healthy_count > 0 else "neutral",
        ), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(metric_card(
            "異常", str(report.unhealthy_count),
            status="negative" if report.unhealthy_count > 0 else "positive",
        ), unsafe_allow_html=True)
    with cols[3]:
        avg_score = (
            sum(s.score for s in report.strategies) / len(report.strategies)
            if report.strategies else 0
        )
        st.markdown(metric_card(
            "平均健康分", f"{avg_score:.0f}",
            status="positive" if avg_score >= 60 else "warning",
        ), unsafe_allow_html=True)

    # 策略健康度表格
    st.divider()
    rows = []
    for s in sorted(report.strategies, key=lambda x: x.score, reverse=True):
        rows.append({
            "策略": s.name,
            "健康分": s.score,
            "勝率": f"{s.win_rate:.0%}",
            "均報酬%": f"{s.avg_return:+.2f}",
            "最大回撤%": f"{s.max_drawdown:.2f}",
            "交易次數": s.trade_count,
            "權重調整": f"{s.weight_adjustment:.2f}",
            "狀態": "✅ 健康" if s.is_healthy else "⚠️ 異常",
        })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "健康分": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
        },
    )

    # 健康度圓餅圖 + 柱狀圖
    col_a, col_b = st.columns(2)

    with col_a:
        scores = [s.score for s in report.strategies]
        names = [s.name for s in report.strategies]
        fig = go.Figure(go.Bar(
            x=names, y=scores,
            marker_color=[
                c["positive"] if s >= 60 else c["warning"] if s >= 40 else c["negative"]
                for s in scores
            ],
            text=[f"{s:.0f}" for s in scores],
            textposition="outside",
        ))
        fig = _apply_layout(fig, "策略健康分", 320)
        fig.add_hline(y=60, line_dash="dash", line_color="#4caf50",
                      annotation_text="健康閾值")
        st.plotly_chart(fig, width="stretch")

    with col_b:
        win_rates = [s.win_rate * 100 for s in report.strategies]
        fig2 = go.Figure(go.Bar(
            x=names, y=win_rates,
            marker_color=[
                c["positive"] if w >= 50 else c["warning"] if w >= 40 else c["negative"]
                for w in win_rates
            ],
            text=[f"{w:.0f}%" for w in win_rates],
            textposition="outside",
        ))
        fig2 = _apply_layout(fig2, "策略勝率", 320)
        fig2.add_hline(y=50, line_dash="dash", line_color="#4caf50",
                       annotation_text="50% 基準線")
        st.plotly_chart(fig2, width="stretch")

    # 行動建議
    if report.action_items:
        st.divider()
        st.subheader("⚠️ 行動建議")
        for item in report.action_items:
            st.warning(item)


def render() -> None:
    st.title("🔬 因子健檢 & 策略健康度")
    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
<span class="legend-good">IC (Information Coefficient)</span>：因子預測力（與未來報酬的相關係數），<span class="legend-good">|IC|&gt;0.05 有效</span>、<span class="legend-good">|IC|&gt;0.1 強效</span>、<span class="legend-bad">&lt;0.03 無效</span><br>
<span class="legend-good">ICIR</span>：IC 穩定度（IC均值 / IC標準差），<span class="legend-good">&gt;0.5 穩定有效</span>、<span class="legend-warn">0~0.5 不穩定</span>、<span class="legend-bad">&lt;0 反向因子</span><br>
<span class="legend-neutral">衰減天數</span>：因子效力持續天數，越長越適合中長期策略，越短適合短線使用<br>
<span class="legend-good">因子權重</span>：建議配置比例，<span class="legend-good">權重高 = 該因子近期表現佳</span>，可加大參考比重<br>
<span class="legend-good">策略健康分</span>：綜合評估策略狀態，<span class="legend-good">&gt;70 健康</span>、<span class="legend-warn">50~70 注意</span>、<span class="legend-bad">&lt;50 需調整</span>
</div>
""", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📊 因子 ICIR", "🏥 策略健康度"])

    with tab1:
        _render_factor_section()

    with tab2:
        _render_strategy_health()
