"""P-16 因子分析與策略 — 因子策略庫 / ICIR 排名 / 多因子組合 / 策略健康度。"""

from __future__ import annotations

import logging

import numpy as np
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

# ── 內建因子定義（fallback，factor_strategies 模組不存在時使用）────

_FACTOR_CATEGORIES = {
    "價值因子": {
        "color": "#2196f3",
        "factors": [
            {"name": "PE_ratio", "display": "本益比", "direction": -1,
             "desc": "越低代表越便宜，適合價值投資選股"},
            {"name": "PB_ratio", "display": "股價淨值比", "direction": -1,
             "desc": "低 PB 表示股價相對資產便宜"},
            {"name": "Dividend_yield", "display": "殖利率", "direction": 1,
             "desc": "現金殖利率越高，收益越穩定"},
        ],
    },
    "動能因子": {
        "color": "#ff1744",
        "factors": [
            {"name": "RS_20d", "display": "20日相對強度", "direction": 1,
             "desc": "近20日漲幅相對大盤的強弱"},
            {"name": "MA_alignment", "display": "均線排列", "direction": 1,
             "desc": "短中長期均線多頭排列得分"},
            {"name": "MACD_hist", "display": "MACD柱狀體", "direction": 1,
             "desc": "MACD柱狀體方向與力道"},
        ],
    },
    "技術因子": {
        "color": "#ff9100",
        "factors": [
            {"name": "RSI_14", "display": "RSI(14)", "direction": 1,
             "desc": "相對強弱指標，50以上偏多"},
            {"name": "KD_cross", "display": "KD交叉", "direction": 1,
             "desc": "K線黃金交叉/死亡交叉訊號"},
            {"name": "OBV_slope", "display": "OBV斜率", "direction": 1,
             "desc": "量能趨勢方向，正值為量增"},
        ],
    },
    "籌碼因子": {
        "color": "#4caf50",
        "factors": [
            {"name": "Fund_flow", "display": "法人買賣超", "direction": 1,
             "desc": "三大法人近期淨買超張數"},
            {"name": "Chip_concentration", "display": "籌碼集中度", "direction": 1,
             "desc": "大戶持股比例變化"},
            {"name": "Margin_ratio", "display": "券資比", "direction": -1,
             "desc": "融券/融資比，高券資比有軋空潛力"},
        ],
    },
    "量能因子": {
        "color": "#9c27b0",
        "factors": [
            {"name": "Volume_ratio", "display": "量比", "direction": 1,
             "desc": "今日量 vs 近5日均量，>1.5 為放量"},
            {"name": "Volume_breakout", "display": "量能突破", "direction": 1,
             "desc": "成交量突破近20日高點"},
            {"name": "Turnover_rate", "display": "換手率", "direction": 1,
             "desc": "日成交量/流通股數，衡量活躍度"},
        ],
    },
    "產業因子": {
        "color": "#00bcd4",
        "factors": [
            {"name": "Industry_rotation", "display": "產業輪動", "direction": 1,
             "desc": "所屬產業近期相對大盤強弱"},
            {"name": "Sector_momentum", "display": "族群動能", "direction": 1,
             "desc": "同族群個股平均漲幅"},
            {"name": "Export_fx", "display": "匯率敏感度", "direction": -1,
             "desc": "台幣升值對出口股的負面影響"},
        ],
    },
}

# ── 內建多因子組合策略 ─────────────────────────────

_MULTI_FACTOR_STRATEGIES = [
    {
        "name": "價值成長",
        "desc": "低本益比 + 高殖利率 + 法人買超，適合穩健投資人",
        "factors": {"PE_ratio": 0.30, "Dividend_yield": 0.25,
                    "Fund_flow": 0.25, "RS_20d": 0.20},
        "rebalance": "月",
        "top_n": 10,
    },
    {
        "name": "動能突破",
        "desc": "均線多頭排列 + 量能突破 + 相對強度，追強勢股",
        "factors": {"MA_alignment": 0.30, "Volume_breakout": 0.25,
                    "RS_20d": 0.25, "MACD_hist": 0.20},
        "rebalance": "週",
        "top_n": 8,
    },
    {
        "name": "籌碼優選",
        "desc": "法人買超 + 籌碼集中 + 量比放大，跟著大戶走",
        "factors": {"Fund_flow": 0.35, "Chip_concentration": 0.30,
                    "Volume_ratio": 0.20, "RS_20d": 0.15},
        "rebalance": "週",
        "top_n": 10,
    },
    {
        "name": "技術綜合",
        "desc": "RSI + KD + MACD + OBV 四指標共振，技術面全面確認",
        "factors": {"RSI_14": 0.25, "KD_cross": 0.25,
                    "MACD_hist": 0.25, "OBV_slope": 0.25},
        "rebalance": "週",
        "top_n": 8,
    },
    {
        "name": "產業輪動",
        "desc": "產業輪動 + 族群動能 + 法人買超，抓住產業趨勢",
        "factors": {"Industry_rotation": 0.35, "Sector_momentum": 0.25,
                    "Fund_flow": 0.25, "Volume_ratio": 0.15},
        "rebalance": "月",
        "top_n": 12,
    },
    {
        "name": "軋空獵手",
        "desc": "高券資比 + 法人買超 + 量能突破，瞄準軋空行情",
        "factors": {"Margin_ratio": 0.35, "Fund_flow": 0.30,
                    "Volume_breakout": 0.20, "RS_20d": 0.15},
        "rebalance": "週",
        "top_n": 5,
    },
    {
        "name": "低估反彈",
        "desc": "低 PB + RSI 超賣 + OBV 回升，撿便宜反彈股",
        "factors": {"PB_ratio": 0.30, "RSI_14": 0.25,
                    "OBV_slope": 0.25, "Dividend_yield": 0.20},
        "rebalance": "月",
        "top_n": 10,
    },
    {
        "name": "全方位均衡",
        "desc": "價值 + 動能 + 籌碼 + 技術均衡配置，分散風險",
        "factors": {"PE_ratio": 0.15, "RS_20d": 0.15,
                    "Fund_flow": 0.15, "RSI_14": 0.15,
                    "Volume_ratio": 0.15, "Industry_rotation": 0.10,
                    "MA_alignment": 0.15},
        "rebalance": "月",
        "top_n": 15,
    },
]


def _get_all_factors() -> list[dict]:
    """取得所有因子的扁平清單。"""
    all_factors = []
    for cat_name, cat_data in _FACTOR_CATEGORIES.items():
        for f in cat_data["factors"]:
            all_factors.append({**f, "category": cat_name, "color": cat_data["color"]})
    return all_factors


# ── Tab 1: 因子策略庫 ──────────────────────────────

def _render_factor_library() -> None:
    """展示 6 大類 18 個因子的定義卡片。"""

    # 嘗試從 factor_strategies 模組載入
    _lib = None
    try:
        from atlas.strategy.factor_strategies import (
            FactorCategory,
            FactorStrategyLibrary,
        )
        _lib = FactorStrategyLibrary()
    except ImportError:
        pass

    if _lib is not None:
        # 真實模組可用：使用 FactorStrategyLibrary
        try:
            categories = list(FactorCategory)
            for cat in categories:
                st.subheader(f"{cat.value}")
                factors = _lib.get_by_category(cat)
                cols = st.columns(3)
                for i, f in enumerate(factors):
                    with cols[i % 3]:
                        with st.container(border=True):
                            d_icon = "📈" if f.direction == 1 else "📉"
                            st.markdown(f"**{d_icon} {f.display_name}**")
                            st.caption(f.description)
            return
        except Exception as e:
            logger.warning("FactorStrategyLibrary 載入失敗，使用內建定義: %s", e)

    # fallback: 內建因子定義
    st.caption("因子策略庫 — 6 大類 18 個因子定義")
    st.markdown("""
<div class="legend-box">
<strong>方向說明</strong><br>
📈 <span class="legend-good">正向因子</span>：數值越大越好（如動能、法人買超）<br>
📉 <span class="legend-bad">反向因子</span>：數值越小越好（如本益比、股價淨值比）
</div>
""", unsafe_allow_html=True)

    for cat_name, cat_data in _FACTOR_CATEGORIES.items():
        cat_color = cat_data["color"]
        st.markdown(
            f'<h3 style="color:{cat_color}; margin-top:1.2rem;">'
            f'{cat_name}</h3>',
            unsafe_allow_html=True,
        )
        cols = st.columns(3)
        for i, f in enumerate(cat_data["factors"]):
            with cols[i % 3]:
                with st.container(border=True):
                    d_icon = "📈" if f["direction"] == 1 else "📉"
                    st.markdown(f"**{d_icon} {f['display']}**")
                    st.markdown(
                        f'<span style="background:{cat_color}22; '
                        f'color:{cat_color}; padding:2px 8px; '
                        f'border-radius:4px; font-size:12px;">'
                        f'{cat_name}</span>',
                        unsafe_allow_html=True,
                    )
                    st.caption(f["desc"])


# ── Tab 2: 因子 ICIR 排名 ─────────────────────────

def _render_factor_icir() -> None:
    """因子 ICIR 排名：嘗試真實計算，失敗時用模擬資料。"""
    c = get_colors()

    st.markdown("""
<div class="legend-box">
<strong>指標說明</strong><br>
<span class="legend-good">IC均值</span>：因子與未來報酬的相關性，\
<span class="legend-good">>=0.03 有預測力</span>、\
<span class="legend-bad"><0.03 無效</span><br>
<span class="legend-good">ICIR</span>：IC均值/IC標準差，衡量因子穩定性，\
<span class="legend-good">>=0.5 穩定有效</span>、\
<span class="legend-warn">0~0.5 不穩定</span>、\
<span class="legend-bad"><0 反向</span><br>
✅ = IC>=0.03 且 ICIR>=0.5（穩定有效因子）  ❌ = 不符合條件
</div>
""", unsafe_allow_html=True)

    # 嘗試用 FactorPipeline 做真實計算
    real_data = False
    try:
        from atlas.strategy.factor_strategies import FactorPipeline
        pipeline = FactorPipeline()

        with st.spinner("正在計算因子 ICIR..."):
            result = pipeline.run_full_evaluation()
            if result and hasattr(result, "factors") and result.factors:
                real_data = True
                _render_icir_from_report(result, c)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("FactorPipeline 執行失敗: %s", e)

    if not real_data:
        _render_icir_demo(c)


def _render_icir_from_report(report, c: dict) -> None:
    """從真實 FactorReport 渲染 ICIR 排名。"""
    rows = []
    for f in report.factors:
        status = "✅" if f.is_valid else "❌"
        rows.append({
            "因子": f.name,
            "IC均值": round(f.ic_mean, 4),
            "IC標準差": round(f.ic_std, 4),
            "ICIR": round(f.icir, 2),
            "衰退期數": f.decay_periods,
            "有效": status,
        })
    df = pd.DataFrame(rows).sort_values("ICIR", ascending=False)
    df.insert(0, "排名", range(1, len(df) + 1))
    _render_icir_charts(df, c, is_demo=False)


def _render_icir_demo(c: dict) -> None:
    """模擬資料展示 ICIR 排名。"""
    st.caption("⚠️ 模擬資料 — FactorPipeline 模組尚未接入，以下為 demo 展示")

    engine = get_factor_mining_engine()  # noqa: F841

    np.random.seed(42)
    all_factors = _get_all_factors()
    factor_names = [f["display"] for f in all_factors]

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
            "衰退期數": 0,
            "有效": "✅" if abs(ic_mean) >= 0.03 and abs(icir) >= 0.5 else "❌",
        })

    df = pd.DataFrame(demo_stats).sort_values("ICIR", ascending=False)
    df.insert(0, "排名", range(1, len(df) + 1))
    _render_icir_charts(df, c, is_demo=True)


def _render_icir_charts(df: pd.DataFrame, c: dict, *, is_demo: bool) -> None:
    """ICIR 柱狀圖 + 明細表共用渲染。"""
    fig = go.Figure(go.Bar(
        x=df["因子"].tolist(),
        y=df["ICIR"].tolist(),
        marker_color=[
            c["positive"] if v >= 0.5 else c["warning"] if v >= 0 else c["negative"]
            for v in df["ICIR"]
        ],
        text=[f"{v:.2f}" for v in df["ICIR"]],
        textposition="outside",
    ))
    fig = _apply_layout(fig, "因子 ICIR 排名", 380)
    fig.update_layout(
        xaxis=dict(tickangle=-45),
        yaxis=dict(title="ICIR"),
    )
    fig.add_hline(
        y=0.5, line_dash="dash", line_color="#4caf50",
        annotation_text="有效閾值 (0.5)",
    )
    fig.add_hline(y=0, line_dash="solid", line_color="#666")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "ICIR": st.column_config.NumberColumn(format="%.2f"),
            "IC均值": st.column_config.NumberColumn(format="%.4f"),
            "IC標準差": st.column_config.NumberColumn(format="%.4f"),
        },
    )

    valid_count = len(df[df["有效"] == "✅"])
    total = len(df)
    st.caption(f"有效因子: {valid_count}/{total} | ICIR 閾值: 0.5 | IC 閾值: 0.03")


# ── Tab 3: 多因子組合策略 ─────────────────────────

def _render_multi_factor() -> None:
    """多因子組合策略展示與執行。"""
    c = get_colors()

    # 嘗試載入真實 MultiFactorEngine
    _engine = None
    try:
        from atlas.strategy.factor_strategies import MultiFactorEngine
        _engine = MultiFactorEngine()
    except ImportError:
        pass

    st.markdown("""
<div class="legend-box">
<strong>使用說明</strong><br>
選擇預設策略組合，查看因子權重配置與策略特性。<br>
每個策略由多個因子加權組合，根據綜合得分選出 Top N 個股。
</div>
""", unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("策略清單")
        strategy_names = [s["name"] for s in _MULTI_FACTOR_STRATEGIES]
        selected_idx = 0
        for i, s in enumerate(_MULTI_FACTOR_STRATEGIES):
            if st.button(
                f"{'📌 ' if i == selected_idx else ''}{s['name']}",
                key=f"mf_btn_{i}",
                use_container_width=True,
            ):
                st.session_state["mf_selected"] = i

        selected_idx = st.session_state.get("mf_selected", 0)

    strategy = _MULTI_FACTOR_STRATEGIES[selected_idx]

    with col_right:
        st.subheader(f"📋 {strategy['name']}")
        with st.container(border=True):
            st.markdown(f"**策略說明：** {strategy['desc']}")
            c1, c2 = st.columns(2)
            with c1:
                st.metric("換股頻率", strategy["rebalance"])
            with c2:
                st.metric("選股數量", f"{strategy['top_n']} 檔")

        # 因子權重柱狀圖
        st.subheader("因子權重配置")
        factor_labels = []
        factor_weights = []
        all_factors_map = {f["name"]: f["display"] for f in _get_all_factors()}
        for fname, w in strategy["factors"].items():
            label = all_factors_map.get(fname, fname)
            factor_labels.append(label)
            factor_weights.append(w * 100)

        fig = go.Figure(go.Bar(
            y=factor_labels,
            x=factor_weights,
            orientation="h",
            marker_color=[
                c.get("accent", "#00d4aa") if w >= 25
                else c.get("accent_secondary", "#667eea") if w >= 15
                else c.get("neutral", "#78909c")
                for w in factor_weights
            ],
            text=[f"{w:.0f}%" for w in factor_weights],
            textposition="outside",
        ))
        fig = _apply_layout(fig, "", 280)
        fig.update_layout(
            xaxis=dict(title="權重 (%)", range=[0, max(factor_weights) * 1.3]),
            yaxis=dict(autorange="reversed"),
            margin=dict(l=120, r=30, t=20, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

        # 執行選股按鈕
        if _engine is not None:
            if st.button("🚀 執行選股", type="primary", key="mf_run"):
                with st.spinner("正在計算多因子選股..."):
                    try:
                        result = _engine.run(strategy)
                        if result:
                            st.success(f"選出 {len(result)} 檔標的")
                            st.dataframe(
                                pd.DataFrame(result),
                                hide_index=True,
                                use_container_width=True,
                            )
                    except Exception as e:
                        st.error(f"選股失敗: {e}")
        else:
            st.info(
                "MultiFactorEngine 尚未接入，"
                "執行選股功能待模組完成後啟用。"
            )


# ── Tab 4: 策略健康度 ─────────────────────────────

def _render_strategy_health() -> None:
    """策略健康度日報（保留核心邏輯，card 化 UI）。"""
    c = get_colors()

    engine = get_daily_backtest_engine()

    st.markdown("""
<div class="legend-box">
<strong>指標說明</strong><br>
<span class="legend-good">健康分</span>：0~100 綜合評分，\
<span class="legend-good">>=60 健康</span>、\
<span class="legend-warn">40~60 需關注</span>、\
<span class="legend-bad"><40 異常</span><br>
<span class="legend-good">勝率</span>：獲利交易佔比，\
<span class="legend-good">>=50% 正常</span>、\
<span class="legend-bad"><40% 偏低</span><br>
<span class="legend-good">均報酬%</span>：每筆交易平均損益，\
<span class="legend-good">>0 獲利</span>、\
<span class="legend-bad"><0 虧損</span><br>
<span class="legend-good">權重調整</span>：系統建議的倉位調整係數，\
<span class="legend-good">>1 可加碼</span>、\
<span class="legend-bad"><1 應減碼</span>
</div>
""", unsafe_allow_html=True)

    # 嘗試從 paper_trading 取真實資料
    real_trades = None
    try:
        if "paper_trades" in st.session_state:
            real_trades = st.session_state["paper_trades"]
    except Exception:
        pass

    if real_trades and isinstance(real_trades, dict) and len(real_trades) > 0:
        strategies = real_trades
        st.caption("資料來源：模擬交易紀錄")
    else:
        # 模擬策略交易資料（fallback）
        st.caption("⚠️ 模擬資料 — 無真實交易紀錄，以下為 demo 展示")
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

    # 概覽卡片（card 化）
    with st.container(border=True):
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

    # 健康度圓環（gauge_rings）
    try:
        from atlas.presentation.components.analysis_charts import gauge_rings
        gauge_metrics = [
            {"name": s.name, "value": int(s.score)}
            for s in report.strategies
        ]
        if gauge_metrics:
            fig_gauge = gauge_rings(gauge_metrics, columns=5, height=220)
            st.plotly_chart(fig_gauge, use_container_width=True)
    except Exception:
        pass  # gauge_rings 不可用時跳過

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
        use_container_width=True,
        column_config={
            "健康分": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.0f",
            ),
        },
    )

    # 健康度柱狀圖 + 勝率柱狀圖
    col_a, col_b = st.columns(2)

    with col_a:
        with st.container(border=True):
            scores = [s.score for s in report.strategies]
            names = [s.name for s in report.strategies]
            fig = go.Figure(go.Bar(
                x=names, y=scores,
                marker_color=[
                    c["positive"] if s >= 60
                    else c["warning"] if s >= 40
                    else c["negative"]
                    for s in scores
                ],
                text=[f"{s:.0f}" for s in scores],
                textposition="outside",
            ))
            fig = _apply_layout(fig, "策略健康分", 320)
            fig.add_hline(
                y=60, line_dash="dash", line_color="#4caf50",
                annotation_text="健康閾值",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        with st.container(border=True):
            win_rates = [s.win_rate * 100 for s in report.strategies]
            fig2 = go.Figure(go.Bar(
                x=names, y=win_rates,
                marker_color=[
                    c["positive"] if w >= 50
                    else c["warning"] if w >= 40
                    else c["negative"]
                    for w in win_rates
                ],
                text=[f"{w:.0f}%" for w in win_rates],
                textposition="outside",
            ))
            fig2 = _apply_layout(fig2, "策略勝率", 320)
            fig2.add_hline(
                y=50, line_dash="dash", line_color="#4caf50",
                annotation_text="50% 基準線",
            )
            st.plotly_chart(fig2, use_container_width=True)

    # 行動建議
    if report.action_items:
        st.divider()
        st.subheader("⚠️ 行動建議")
        for item in report.action_items:
            st.warning(item)


# ── 主入口 ─────────────────────────────────────────

def render() -> None:
    st.title("🔬 因子分析與策略")
    st.markdown("""
<div class="legend-box">
<strong>頁面導覽</strong><br>
<span class="legend-good">因子策略庫</span>：6大類18個因子的定義與方向<br>
<span class="legend-good">因子 ICIR 排名</span>：因子預測力與穩定性評估<br>
<span class="legend-good">多因子組合策略</span>：8個預設策略的權重配置與選股<br>
<span class="legend-good">策略健康度</span>：策略近期表現的綜合健康分數
</div>
""", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 因子策略庫",
        "📈 因子 ICIR 排名",
        "🏆 多因子組合策略",
        "🏥 策略健康度",
    ])

    with tab1:
        _render_factor_library()

    with tab2:
        _render_factor_icir()

    with tab3:
        _render_multi_factor()

    with tab4:
        _render_strategy_health()
