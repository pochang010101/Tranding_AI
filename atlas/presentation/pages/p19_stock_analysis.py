"""P-19 個股分析儀表板 — 類似 ECF AI Trading System 單股 dashboard 佈局。"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from atlas.presentation.components.analysis_charts import (
    energy_bar,
    gauge_rings,
    institutional_flow_chart,
    prediction_fan_chart,
    radar_chart,
    volume_profile_chart,
)
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    TW_TOP_STOCKS,
    fetch_institutional_flow,
    fetch_stock_data,
    fetch_stock_quote,
    get_indicator_lib,
    get_price_level_calc,
)

logger = logging.getLogger(__name__)


def _select_stock() -> str:
    """股票選擇器（熱門股下拉 + 自訂代碼）。"""
    stock_labels = [f"{code} {name}" for code, name in TW_TOP_STOCKS]
    col_sel, col_custom = st.columns([3, 2])
    with col_sel:
        selected_label = st.selectbox(
            "熱門股票", options=["（自訂代碼）"] + stock_labels, index=1,
            key="p19_stock_select",
        )
    with col_custom:
        if selected_label == "（自訂代碼）":
            custom_code = st.text_input(
                "自訂股票代碼", value="2330", placeholder="e.g. 2330",
                key="p19_custom_code",
            )
            code = custom_code.strip()
        else:
            code = selected_label.split()[0]
            st.text_input("股票代碼（唯讀）", value=code, disabled=True,
                          key="p19_code_ro")
    return code


def _get_trend_label(df: pd.DataFrame) -> tuple[str, str]:
    """依 MA 判斷趨勢。回傳 (趨勢文字, status)。"""
    if len(df) < 55:
        return "資料不足", "neutral"
    ma8 = df["MA8"].iloc[-1] if "MA8" in df.columns else 0
    ma21 = df["MA21"].iloc[-1] if "MA21" in df.columns else 0
    close = df["close"].iloc[-1]
    if ma8 > ma21 and close > ma8:
        return "多頭排列", "positive"
    if ma8 < ma21 and close < ma8:
        return "空頭排列", "negative"
    return "盤整震盪", "neutral"


def _get_short_term_label(df: pd.DataFrame) -> tuple[str, str]:
    """短線狀態：RSI + KD。"""
    rsi = df["RSI14"].iloc[-1] if "RSI14" in df.columns else 50
    if pd.isna(rsi):
        rsi = 50
    if rsi > 70:
        return "短線過熱", "negative"
    if rsi < 30:
        return "短線超賣", "positive"
    return "短線中性", "neutral"


def _phase_to_light(phase_str: str) -> tuple[str, str, str]:
    """主力階段 → (燈號色, 中文, status)。"""
    mapping = {
        "accumulation": ("🟢", "吸貨", "positive"),
        "markup":       ("🟢", "拉抬", "positive"),
        "shakeout":     ("🟡", "洗盤", "neutral"),
        "distribution": ("🔴", "出貨", "negative"),
        "unknown":      ("⚪", "不明", "neutral"),
    }
    return mapping.get(phase_str, ("⚪", "不明", "neutral"))


def _calc_bull_bear(df: pd.DataFrame) -> tuple[float, float]:
    """多空能量：近 20 日漲跌比例。"""
    if len(df) < 20:
        return 50.0, 50.0
    recent = df["close"].iloc[-20:]
    changes = recent.diff().dropna()
    up = (changes > 0).sum()
    total = len(changes)
    if total == 0:
        return 50.0, 50.0
    bull = round(up / total * 100, 1)
    bear = round(100 - bull, 1)
    return bull, bear


def _is_dark_theme() -> bool:
    """判斷當前是否為深色主題。"""
    return st.session_state.get("theme", "dark") == "dark"


def render() -> None:  # noqa: C901
    st.title("🔎 個股分析儀表板")

    # ── Card 化 CSS：覆蓋 st.container(border=True) 樣式 ──
    st.markdown("""
<style>
[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(30, 35, 45, 0.6) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    padding: 12px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    backdrop-filter: blur(8px);
    margin-bottom: 8px;
}
[data-testid="stAppViewContainer"][data-theme="light"]
    [data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255, 255, 255, 0.92) !important;
    border: 1px solid rgba(0, 0, 0, 0.1) !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
</style>
""", unsafe_allow_html=True)

    st.markdown("""
<div class="legend-box">
<strong>功能說明</strong><br>
本頁整合 AI 決策核心、多維雷達圖、主力燈號、預測路徑、成本分布、法人買賣超、
隔日沖風險、健康度評估、AI 信心維度等 11 個分析區塊。<br>
<span class="legend-good">紅色指標</span> = 偏多/正面 |
<span class="legend-bad">綠色指標</span> = 偏空/負面 |
<span class="legend-warn">橘色指標</span> = 警示/中性
</div>
""", unsafe_allow_html=True)

    c = get_colors()
    dark = _is_dark_theme()
    code = _select_stock()

    # ── 取得基礎資料 ───────────────────────────────
    with st.spinner(f"載入 {code} 資料中…"):
        ohlcv_df = fetch_stock_data(code, "6mo")

    if ohlcv_df is None or ohlcv_df.empty:
        st.warning(f"無法取得 {code} 的資料，請確認代碼是否正確。")
        return

    ohlcv_df = ohlcv_df.copy()

    # 計算技術指標
    try:
        ind_lib = get_indicator_lib()
        df = ind_lib.calculate_all(ohlcv_df)
    except Exception:
        df = ohlcv_df.copy()

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    close_price = float(last["close"])
    prev_close = float(prev["close"])
    change = close_price - prev_close
    change_pct = change / prev_close * 100 if prev_close else 0

    # 即時報價（補充盤中資料）
    quote: dict = {}
    try:
        quote = fetch_stock_quote(code)
    except Exception:
        pass

    # ══════════════════════════════════════════════
    # Row 0 — 即時報價列
    # ══════════════════════════════════════════════
    with st.container(border=True):
        st.markdown("#### 即時報價")
        r0 = st.columns(7)
        with r0[0]:
            chg_status = "positive" if change >= 0 else "negative"
            st.markdown(
                metric_card("收盤價", f"{close_price:,.2f}", status=chg_status),
                unsafe_allow_html=True,
            )
        with r0[1]:
            st.markdown(
                metric_card("漲跌", f"{change:+.2f}", status=chg_status),
                unsafe_allow_html=True,
            )
        with r0[2]:
            st.markdown(
                metric_card("漲跌%", f"{change_pct:+.2f}%", status=chg_status),
                unsafe_allow_html=True,
            )
        with r0[3]:
            vol = int(last.get("volume", 0))
            st.markdown(
                metric_card("成交量", f"{vol:,}"),
                unsafe_allow_html=True,
            )
        with r0[4]:
            st.markdown(
                metric_card(
                    "振幅",
                    f"{(float(last['high']) - float(last['low'])):.2f}",
                ),
                unsafe_allow_html=True,
            )
        with r0[5]:
            bid = quote.get("day_low", float(last["low"]))
            st.markdown(
                metric_card("最低", f"{float(bid):,.2f}"),
                unsafe_allow_html=True,
            )
        with r0[6]:
            ask = quote.get("day_high", float(last["high"]))
            st.markdown(
                metric_card("最高", f"{float(ask):,.2f}"),
                unsafe_allow_html=True,
            )

    # ══════════════════════════════════════════════
    # Row 1 — 核心分析（3 欄）
    # ══════════════════════════════════════════════
    r1c1, r1c2, r1c3 = st.columns(3)

    # ── 01 AI 決策核心 ─────────────────────────────
    with r1c1:
        with st.container(border=True):
            st.markdown("#### 01 AI 決策核心")
            try:
                trend_text, trend_status = _get_trend_label(df)
                short_text, short_status = _get_short_term_label(df)

                # 主力行為
                try:
                    from atlas.strategy.smart_money_phase import SmartMoneyDetector
                    smc_det = SmartMoneyDetector()
                    smc_result = smc_det.detect(df, code=code)
                    light, phase_cn, phase_status = _phase_to_light(
                        smc_result.phase.value
                    )
                    main_text = f"{light} {phase_cn}"
                except Exception:
                    main_text = "—"
                    phase_status = "neutral"

                # 風險等級
                rsi_val = float(last.get("RSI14", 50)) if not pd.isna(
                    last.get("RSI14", 50)
                ) else 50
                if rsi_val > 80 or rsi_val < 20:
                    risk_text, risk_status = "高風險", "negative"
                elif rsi_val > 70 or rsi_val < 30:
                    risk_text, risk_status = "中風險", "neutral"
                else:
                    risk_text, risk_status = "低風險", "positive"

                st.markdown(
                    metric_card("趨勢判斷", trend_text, status=trend_status),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    metric_card("短線狀態", short_text, status=short_status),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    metric_card("主力行為", main_text, status=phase_status),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    metric_card("風險等級", risk_text, status=risk_status),
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.info(f"AI 決策核心載入中… ({e})")

    # ── 02 多維雷達圖 ─────────────────────────────
    with r1c2:
        with st.container(border=True):
            st.markdown("#### 02 多維雷達圖")
            try:
                # 六維評分
                rsi_score = (
                    max(0, min(100, int(rsi_val))) if rsi_val == rsi_val else 50
                )
                macd_hist = float(last.get("MACD_hist", 0))
                macd_hist = macd_hist if not pd.isna(macd_hist) else 0
                macd_score = max(0, min(100, 50 + int(macd_hist * 10)))

                vol_avg = (
                    float(df["volume"].iloc[-20:].mean()) if len(df) >= 20 else 1
                )
                vol_score = (
                    max(0, min(100, int(vol / vol_avg * 50)))
                    if vol_avg > 0 else 50
                )

                # 趨勢分：MA8 vs MA21 距離
                ma8_v = (
                    float(df["MA8"].iloc[-1])
                    if "MA8" in df.columns else close_price
                )
                ma21_v = (
                    float(df["MA21"].iloc[-1])
                    if "MA21" in df.columns else close_price
                )
                trend_score = max(0, min(
                    100, 50 + int((ma8_v - ma21_v) / close_price * 500)
                ))

                # 波動分（ATR 相對價格）
                atr_val = float(last.get("ATR14", 0))
                atr_val = atr_val if not pd.isna(atr_val) else 0
                atr_pct = atr_val / close_price * 100 if close_price > 0 else 0
                volatility_score = max(0, min(100, int(100 - atr_pct * 20)))

                # 動能分（近 5 日漲幅）
                if len(df) >= 5:
                    ret_5d = (
                        close_price / float(df["close"].iloc[-5]) - 1
                    ) * 100
                    momentum_score = max(0, min(100, 50 + int(ret_5d * 5)))
                else:
                    momentum_score = 50

                categories = [
                    "趨勢", "動能", "量能", "技術(RSI)", "波動", "MACD",
                ]
                values = [
                    trend_score, momentum_score, vol_score,
                    rsi_score, volatility_score, macd_score,
                ]
                overall = int(sum(values) / len(values))
                grade = (
                    "A+" if overall >= 85 else "A" if overall >= 70
                    else "B" if overall >= 55 else "C" if overall >= 40
                    else "D"
                )

                fig = radar_chart(
                    categories, values,
                    title=f"{code} 六維度評分",
                    overall_score=overall,
                    overall_grade=grade,
                    height=380,
                    dark=dark,
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.info(f"雷達圖載入中… ({e})")

    # ── 03 主力燈號 ───────────────────────────────
    with r1c3:
        with st.container(border=True):
            st.markdown("#### 03 主力燈號")
            try:
                from atlas.strategy.smart_money_phase import SmartMoneyDetector
                smc_det = SmartMoneyDetector()
                smc_result = smc_det.detect(df, code=code)
                narrative = smc_det.generate_narrative(smc_result)

                light, phase_cn, _ = _phase_to_light(smc_result.phase.value)
                conf_pct = f"{smc_result.confidence:.0%}"

                st.markdown(
                    f"<div style='text-align:center; font-size:48px;'>"
                    f"{light}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='text-align:center; font-size:24px; "
                    f"font-weight:700; color:{c['text_primary']};'>"
                    f"{phase_cn}（信心 {conf_pct}）</div>",
                    unsafe_allow_html=True,
                )
                st.divider()
                st.markdown(f"**{narrative.headline}**")
                st.write(narrative.conclusion)
                st.caption(f"操作標籤：{narrative.action_tag}")
                st.caption(f"風險提示：{narrative.risk_note}")

                if smc_result.signals:
                    st.markdown("**訊號：**")
                    for sig in smc_result.signals:
                        st.markdown(f"- {sig}")
            except Exception as e:
                st.info(f"主力燈號載入中… ({e})")

    # ══════════════════════════════════════════════
    # Row 2 — 預測與籌碼（3 欄）
    # ══════════════════════════════════════════════
    r2c1, r2c2, r2c3 = st.columns(3)

    # ── 04 AI 預測路徑 ────────────────────────────
    with r2c1:
        with st.container(border=True):
            st.markdown("#### 04 AI 預測路徑")
            try:
                atr_for_fan = (
                    atr_val if atr_val > 0 else close_price * 0.02
                )
                # 簡易機率估算：趨勢 + RSI
                if trend_score > 60:
                    bull_p, range_p, bear_p = 0.50, 0.30, 0.20
                elif trend_score < 40:
                    bull_p, range_p, bear_p = 0.20, 0.30, 0.50
                else:
                    bull_p, range_p, bear_p = 0.33, 0.34, 0.33

                fig = prediction_fan_chart(
                    current_price=close_price,
                    bull_prob=bull_p,
                    range_prob=range_p,
                    bear_prob=bear_p,
                    atr=atr_for_fan,
                    days=10,
                    height=380,
                    dark=dark,
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.info(f"預測路徑載入中… ({e})")

    # ── 05 成本分布圖 ────────────────────────────
    with r2c2:
        with st.container(border=True):
            st.markdown("#### 05 成本分布圖")
            try:
                vp = ind_lib.volume_profile(ohlcv_df, bins=30)
                if not vp.empty:
                    price_levels_list = (
                        vp["price_level"].astype(float).tolist()
                    )
                    volumes_list = vp["volume"].astype(float).tolist()

                    # 支撐壓力
                    plc = get_price_level_calc()
                    pl_result = plc.calculate(ohlcv_df, code=code)
                    support = (
                        pl_result.supports[0] if pl_result.supports else None
                    )
                    resist = (
                        pl_result.resistances[0]
                        if pl_result.resistances else None
                    )

                    fig = volume_profile_chart(
                        price_levels=price_levels_list,
                        volumes=volumes_list,
                        current_price=close_price,
                        support=support,
                        resistance=resist,
                        height=380,
                        dark=dark,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("成本分布資料不足")
            except Exception as e:
                st.info(f"成本分布載入中… ({e})")

    # ── 06 法人買賣超 ────────────────────────────
    with r2c3:
        with st.container(border=True):
            st.markdown("#### 06 法人買賣超")
            try:
                flow = fetch_institutional_flow(code)
                if flow and flow.get("source") != "unavailable":
                    fig = institutional_flow_chart(
                        dates=[flow.get("date", "today")],
                        foreign=[flow.get("foreign_net", 0)],
                        trust=[flow.get("trust_net", 0)],
                        dealer=[flow.get("dealer_net", 0)],
                        total=[flow.get("total_net", 0)],
                        height=380,
                        dark=dark,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("法人買賣超資料暫無法取得")

                # 法人摘要
                st.markdown(
                    f"外資：**{flow.get('foreign_net', 0):+,}** 張 | "
                    f"投信：**{flow.get('trust_net', 0):+,}** 張 | "
                    f"自營：**{flow.get('dealer_net', 0):+,}** 張"
                )
            except Exception as e:
                st.info(f"法人資料載入中… ({e})")

    # ══════════════════════════════════════════════
    # Row 3 — 風險與信心（3 欄）
    # ══════════════════════════════════════════════
    r3c1, r3c2, r3c3 = st.columns(3)

    # ── 07 隔日沖風險 ────────────────────────────
    with r3c1:
        with st.container(border=True):
            st.markdown("#### 07 隔日沖風險")
            try:
                from atlas.strategy.daytrader_risk import DaytraderRiskAnalyzer
                dtr = DaytraderRiskAnalyzer()
                flow_for_dtr = {}
                try:
                    fl = fetch_institutional_flow(code)
                    flow_for_dtr = {
                        "foreign": fl.get("foreign_net", 0),
                        "trust": fl.get("trust_net", 0),
                        "dealer": fl.get("dealer_net", 0),
                        "total": fl.get("total_net", 0),
                    }
                except Exception:
                    pass

                dtr_result = dtr.analyze(
                    code, ohlcv_df, fund_flow_data=flow_for_dtr,
                )

                risk_color = {
                    "高": c["negative"] if "negative" in c else "red",
                    "中": c["warning"],
                    "低": c["positive"] if "positive" in c else "green",
                }.get(dtr_result.risk_level, c["neutral"])

                st.markdown(
                    f"<div style='text-align:center; font-size:48px; "
                    f"font-weight:800; color:{risk_color};'>"
                    f"{dtr_result.risk_score}</div>"
                    f"<div style='text-align:center; font-size:18px; "
                    f"color:{risk_color};'>"
                    f"風險等級：{dtr_result.risk_level}</div>",
                    unsafe_allow_html=True,
                )
                st.divider()
                st.markdown(
                    f"量比：**{dtr_result.volume_ratio:.2f}** | "
                    f"週轉率：**{dtr_result.turnover_rate:.2f}%** | "
                    f"振幅：**{dtr_result.intraday_swing:.2f}%**"
                )
                if dtr_result.signals:
                    for sig in dtr_result.signals:
                        st.warning(sig)
                else:
                    st.success("目前無隔日沖風險訊號")
            except Exception as e:
                st.info(f"隔日沖風險載入中… ({e})")

    # ── 08 健康度評估 ────────────────────────────
    with r3c2:
        with st.container(border=True):
            st.markdown("#### 08 健康度評估")
            try:
                # 五維健康度
                chip_health = max(0, min(100, 50 + trend_score // 2))
                tech_health = max(0, min(100, rsi_score))
                fund_health = max(0, min(100, vol_score))
                vol_health = volatility_score
                inst_health = max(0, min(
                    100, 50 + int(flow.get("total_net", 0) / 100)
                ))

                metrics = [
                    {"name": "籌碼", "value": chip_health},
                    {"name": "技術", "value": tech_health},
                    {"name": "資金", "value": fund_health},
                    {"name": "波動", "value": vol_health},
                    {"name": "法人", "value": inst_health},
                ]
                fig = gauge_rings(
                    metrics, columns=5, height=220, dark=dark,
                )
                st.plotly_chart(fig, use_container_width=True)

                avg_health = int(
                    sum(m["value"] for m in metrics) / len(metrics)
                )
                health_label = (
                    "健康" if avg_health >= 70
                    else "普通" if avg_health >= 50
                    else "偏弱"
                )
                health_status = (
                    "positive" if avg_health >= 70
                    else "neutral" if avg_health >= 50
                    else "negative"
                )
                st.markdown(
                    metric_card(
                        "綜合健康度",
                        f"{avg_health} / 100 — {health_label}",
                        status=health_status,
                    ),
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.info(f"健康度評估載入中… ({e})")

    # ── 09 AI 信心維度 ────────────────────────────
    with r3c3:
        with st.container(border=True):
            st.markdown("#### 09 AI 信心維度")
            try:
                from atlas.application.confidence_score import (
                    ConfidenceScorer,
                )
                scorer = ConfidenceScorer()

                # 判斷市場環境
                if trend_score > 60:
                    market_regime = "BULL"
                elif trend_score < 40:
                    market_regime = "BEAR"
                else:
                    market_regime = "RANGE"

                conf_result = scorer.evaluate(
                    symbol=code,
                    ohlcv_df=ohlcv_df,
                    ml_confidence=None,
                    market_regime=market_regime,
                )

                level_color = {
                    "極高": c["positive"], "高": c["positive"],
                    "中": c["warning"],
                    "低": c["negative"], "極低": c["negative"],
                }.get(conf_result.level, c["neutral"])

                st.markdown(
                    f"<div style='text-align:center; font-size:48px; "
                    f"font-weight:800; color:{level_color};'>"
                    f"{conf_result.overall_score}</div>"
                    f"<div style='text-align:center; font-size:18px; "
                    f"color:{level_color};'>"
                    f"信心等級：{conf_result.level}</div>",
                    unsafe_allow_html=True,
                )
                st.divider()
                for dim in conf_result.dimensions:
                    st.markdown(
                        f"**{dim.name}**：{dim.score} 分 — "
                        f"{dim.description}"
                    )
            except Exception as e:
                st.info(f"AI 信心維度載入中… ({e})")

    # ══════════════════════════════════════════════
    # Row 4 — 多空能量（全寬）
    # ══════════════════════════════════════════════
    r4c1, r4c2 = st.columns([2, 1])

    # ── 10 多空能量條 ────────────────────────────
    with r4c1:
        with st.container(border=True):
            st.markdown("#### 10 多空能量")
            try:
                bull_pct, bear_pct = _calc_bull_bear(df)
                fig = energy_bar(
                    bull_pct, bear_pct, height=100, dark=dark,
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.info(f"多空能量載入中… ({e})")

    # ── 11 主力語義結論 ──────────────────────────
    with r4c2:
        with st.container(border=True):
            st.markdown("#### 11 主力語義結論")
            try:
                from atlas.strategy.smart_money_phase import (
                    SmartMoneyDetector,
                )
                smc_det = SmartMoneyDetector()
                smc_result = smc_det.detect(df, code=code)
                narrative = smc_det.generate_narrative(smc_result)

                headline_color = {
                    "底部吸貨": c["positive"],
                    "強勢拉抬": c["positive"],
                    "洗盤整理": c["warning"],
                    "高檔出貨": c["negative"],
                    "訊號不明": c["neutral"],
                }.get(narrative.headline, c["text_primary"])

                st.markdown(
                    f"<div style='text-align:center; font-size:36px; "
                    f"font-weight:800; color:{headline_color}; "
                    f"padding:16px 0;'>{narrative.headline}</div>",
                    unsafe_allow_html=True,
                )
                st.caption(narrative.action_tag)
            except Exception as e:
                st.info(f"主力語義結論載入中… ({e})")

    # ══════════════════════════════════════════════
    # Row 5 — 大戶/散戶分布（全寬 2 欄）
    # ══════════════════════════════════════════════
    r5c1, r5c2 = st.columns(2)

    # ── 12 大戶趨勢分布 ────────────────────────────
    with r5c1:
        with st.container(border=True):
            st.markdown("#### 12 大戶趨勢分布")
            try:
                from atlas.domain.large_trader_analysis import (
                    LargeTraderAnalyzer,
                )
                from atlas.infrastructure.taifex_large_trader import (
                    LargeTraderFetcher,
                )

                fetcher = LargeTraderFetcher()
                lt_data = fetcher.fetch()
                if lt_data:
                    analyzer = LargeTraderAnalyzer()
                    lt_signal = analyzer.analyze(lt_data)

                    # 大戶買賣盤 gauge
                    lg_metrics = [
                        {"name": "大戶買盤", "value": int(lt_signal.large_buy_pct)},
                        {"name": "散戶買盤", "value": int(lt_signal.retail_buy_pct)},
                        {"name": "散戶賣壓", "value": int(lt_signal.retail_sell_pct)},
                    ]
                    fig = gauge_rings(lg_metrics, columns=3, height=200, dark=dark)
                    st.plotly_chart(fig, use_container_width=True)

                    # 訊號文字
                    sig_color = (
                        c["positive"] if "偏多" in lt_signal.signal
                        else c["negative"] if "偏空" in lt_signal.signal
                        else c["warning"]
                    )
                    st.markdown(
                        f"<div style='text-align:center; font-size:20px; "
                        f"font-weight:700; color:{sig_color};'>"
                        f"大戶：{lt_signal.signal}</div>",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"信心度：{lt_signal.confidence}% | 資料日期：{lt_data.date}")
                else:
                    st.info("大額交易人資料暫無法取得（非交易日或盤中）")
            except Exception as e:
                st.info(f"大戶分布載入中… ({e})")

    # ── 13 散戶動向（反指標）────────────────────────
    with r5c2:
        with st.container(border=True):
            st.markdown("#### 13 散戶動向（反指標）")
            try:
                if lt_data and lt_signal:
                    # 散戶多空能量條
                    retail_bull = lt_signal.retail_buy_pct
                    retail_bear = lt_signal.retail_sell_pct
                    fig = energy_bar(
                        retail_bull, retail_bear,
                        title="散戶多空能量", height=100, dark=dark,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # 散戶訊號
                    retail_color = (
                        c["negative"] if "追漲" in lt_signal.retail_signal
                        else c["positive"] if "殺跌" in lt_signal.retail_signal
                        else c["warning"]
                    )
                    st.markdown(
                        f"<div style='text-align:center; font-size:20px; "
                        f"font-weight:700; color:{retail_color};'>"
                        f"散戶：{lt_signal.retail_signal}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        "<div style='text-align:center; font-size:13px; "
                        "color:gray;'>⚠ 散戶動向為反指標："
                        "散戶追漲時宜謹慎，散戶殺跌時可留意機會</div>",
                        unsafe_allow_html=True,
                    )

                    # 大戶 vs 散戶對比表
                    st.divider()
                    st.markdown(
                        f"| 指標 | 大戶（前十大） | 散戶 |\n"
                        f"|------|:---:|:---:|\n"
                        f"| 買盤 | **{lt_signal.large_buy_pct:.1f}%** "
                        f"| {lt_signal.retail_buy_pct:.1f}% |\n"
                        f"| 賣壓 | **{lt_signal.large_sell_pct:.1f}%** "
                        f"| {lt_signal.retail_sell_pct:.1f}% |\n"
                        f"| 訊號 | {lt_signal.signal} "
                        f"| {lt_signal.retail_signal} |"
                    )
                else:
                    st.info("散戶動向資料暫無法取得")
            except Exception as e:
                st.info(f"散戶動向載入中… ({e})")

    # Footer
    st.divider()
    from datetime import datetime

    from atlas.constants import TW_TZ
    st.caption(
        f"個股：{code} | "
        f"更新時間：{datetime.now(TW_TZ).strftime('%H:%M:%S')} | Atlas v5.0"
    )
