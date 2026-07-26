"""P-18 股期對沖策略 — 基差分析 + 法人期貨 + 綜合策略建議。"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card

logger = logging.getLogger(__name__)

# 熱門標的預設清單
DEFAULT_STOCKS = ["2330", "2317", "2454", "3231", "6669", "2303", "2881"]


def _direction_emoji(direction: str) -> str:
    """方向判定 → emoji。"""
    mapping = {
        "BULLISH": "🟢",
        "BEARISH": "🔴",
        "NEUTRAL": "🟡",
    }
    return mapping.get(direction.upper(), "🟡")


def _direction_color(direction: str) -> str:
    """方向判定 → CSS class。"""
    mapping = {
        "BULLISH": "legend-good",
        "BEARISH": "legend-bad",
        "NEUTRAL": "legend-warn",
    }
    return mapping.get(direction.upper(), "legend-warn")


def _pc_ratio_label(ratio: float) -> tuple[str, str]:
    """P/C Ratio → (判讀文字, status)。"""
    if ratio > 1.0:
        return "恐慌 (反向偏多)", "positive"
    if ratio < 0.6:
        return "過度樂觀 (偏空)", "negative"
    return "正常", "neutral"


def _basis_label(basis: float) -> tuple[str, str]:
    """基差 → (判讀文字, status)。"""
    if basis > 0:
        return f"正價差 +{basis:.0f}", "positive"
    if basis < 0:
        return f"逆價差 {basis:.0f}", "negative"
    return "零基差", "neutral"


def render() -> None:
    st.title("🛡️ 股期對沖策略")

    # ── legend-box 欄位說明 ──
    st.markdown("""
<div class="legend-box">
<strong>功能說明</strong><br>
<span class="legend-good">基差分析</span>：現貨-期貨價差，正價差=樂觀、逆價差=恐慌<br>
<span class="legend-warn">法人期貨</span>：三大法人期貨未平倉淨部位，外資淨多=偏多<br>
<span class="legend-bad">P/C Ratio</span>：PUT/CALL 成交量比，>1.0=市場恐慌(反向指標)、<0.6=過度樂觀<br>
<span class="legend-good">對沖建議</span>：結合籌碼面+期貨面產出買賣策略與停損停利
</div>
""", unsafe_allow_html=True)

    c = get_colors()

    # ══════════════════════════════════════════
    # 區塊 1：大盤期貨儀表板
    # ══════════════════════════════════════════
    st.header("📊 大盤期貨概覽")

    try:
        with st.spinner("載入期貨概覽資料..."):

            @st.cache_data(ttl=300)
            def _fetch_overview() -> dict:
                try:
                    from atlas.application.hedge_advisor import HedgeAdvisor

                    advisor = HedgeAdvisor()
                    return advisor.market_overview()
                except ImportError:
                    return {}

            overview = _fetch_overview()

        if overview:
            futures_close = overview.get("futures_close", 0)
            basis = overview.get("basis", 0)
            foreign_net = overview.get("foreign_net_oi", 0)
            pc_ratio = overview.get("pc_ratio", 0.0)
            direction = overview.get("direction", "NEUTRAL")
            confidence = overview.get("confidence", 0)

            basis_text, basis_status = _basis_label(basis)
            pc_text, pc_status = _pc_ratio_label(pc_ratio)

            cols = st.columns(4)
            with cols[0]:
                st.markdown(metric_card(
                    "台指期收盤", f"{futures_close:,.0f}",
                    delta=basis_text,
                    status=basis_status,
                ), unsafe_allow_html=True)
            with cols[1]:
                net_status = "positive" if foreign_net > 0 else "negative" if foreign_net < 0 else "neutral"
                st.markdown(metric_card(
                    "外資期貨淨部位", f"{foreign_net:+,.0f} 口",
                    status=net_status,
                ), unsafe_allow_html=True)
            with cols[2]:
                st.markdown(metric_card(
                    "P/C Ratio", f"{pc_ratio:.2f}",
                    delta=pc_text,
                    status=pc_status,
                ), unsafe_allow_html=True)
            with cols[3]:
                dir_status = (
                    "positive" if direction == "BULLISH"
                    else "negative" if direction == "BEARISH"
                    else "neutral"
                )
                st.markdown(metric_card(
                    "大盤方向判定", f"{_direction_emoji(direction)} {direction}",
                    delta=f"信心度 {confidence}%",
                    status=dir_status,
                ), unsafe_allow_html=True)

            # 三大法人期貨未平倉表格
            institution_data = overview.get("institution_oi", [])
            if institution_data:
                inst_df = pd.DataFrame(institution_data)
                display_cols = {
                    "identity": "法人",
                    "long_position": "多方未平倉",
                    "short_position": "空方未平倉",
                    "net_position": "淨部位",
                }
                rename_map = {k: v for k, v in display_cols.items() if k in inst_df.columns}
                inst_df = inst_df.rename(columns=rename_map)
                st.dataframe(
                    inst_df[[v for v in display_cols.values() if v in inst_df.columns]],
                    hide_index=True,
                    use_container_width=True,
                )
        else:
            st.info("期貨概覽資料暫無法取得（HedgeAdvisor 模組尚未建置或非交易時段）。")

    except Exception as exc:
        logger.warning("載入期貨概覽失敗: %s", exc)
        st.warning(f"期貨概覽資料載入失敗：{exc}")

    # ══════════════════════════════════════════
    # 區塊 2：個股對沖分析
    # ══════════════════════════════════════════
    st.divider()
    st.header("🎯 個股對沖分析")

    col_code, col_qty = st.columns(2)
    with col_code:
        stock_code = st.text_input("股票代碼", value="2330", key="hedge_stock_code")
    with col_qty:
        hold_lots = st.number_input("持有張數", min_value=1, value=1, step=1, key="hedge_hold_lots")

    analyze_clicked = st.button("分析對沖策略", key="hedge_analyze_btn", type="primary")

    if analyze_clicked and stock_code.strip():
        code = stock_code.strip()
        try:
            with st.spinner(f"分析 {code} 對沖策略..."):

                @st.cache_data(ttl=300)
                def _fetch_stock_hedge(_code: str, _lots: int) -> dict:
                    try:
                        from atlas.application.hedge_advisor import HedgeAdvisor

                        advisor = HedgeAdvisor()
                        return advisor.analyze_stock(_code, _lots)
                    except ImportError:
                        return {}

                result = _fetch_stock_hedge(code, hold_lots)

            if result:
                # ── 籌碼面指標 ──
                chip = result.get("chip_data", {})
                card_cols = st.columns(4)
                with card_cols[0]:
                    margin_bal = chip.get("margin_balance", 0)
                    margin_chg = chip.get("margin_change", 0)
                    chg_status = "negative" if margin_chg > 500 else "positive" if margin_chg < -500 else "neutral"
                    st.markdown(metric_card(
                        "融資餘額", f"{margin_bal:,} 張",
                        delta=f"增減 {margin_chg:+,}",
                        status=chg_status,
                    ), unsafe_allow_html=True)
                with card_cols[1]:
                    short_bal = chip.get("short_balance", 0)
                    sr_ratio = chip.get("short_margin_ratio", 0.0)
                    sr_status = "positive" if sr_ratio > 30 else "neutral"
                    st.markdown(metric_card(
                        "融券餘額", f"{short_bal:,} 張",
                        delta=f"券資比 {sr_ratio:.1f}%",
                        status=sr_status,
                    ), unsafe_allow_html=True)
                with card_cols[2]:
                    inst_net = chip.get("institutional_net", 0)
                    inst_status = "positive" if inst_net > 0 else "negative" if inst_net < 0 else "neutral"
                    st.markdown(metric_card(
                        "法人買賣超", f"{inst_net:+,} 張",
                        status=inst_status,
                    ), unsafe_allow_html=True)
                with card_cols[3]:
                    lending = chip.get("lending_balance", 0)
                    st.markdown(metric_card(
                        "借券餘額", f"{lending:,} 張",
                        status="neutral",
                    ), unsafe_allow_html=True)

                # ── 策略建議卡片 ──
                strategy = result.get("strategy", {})
                direction = strategy.get("direction", "NEUTRAL")
                confidence = strategy.get("confidence", 0)
                dir_cls = _direction_color(direction)

                st.markdown(
                    f'<div class="legend-box">'
                    f'<strong>方向判定：</strong>'
                    f'<span class="{dir_cls}">'
                    f'{_direction_emoji(direction)} {direction} — 信心度 {confidence}%'
                    f'</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                strategy_type = strategy.get("strategy_type", "—")
                spot_action = strategy.get("spot_action", "—")
                futures_action = strategy.get("futures_action", "—")
                entry_price = strategy.get("entry_price", 0)
                stop_loss = strategy.get("stop_loss", 0)
                take_profit = strategy.get("take_profit", 0)
                risk_reward = strategy.get("risk_reward_ratio", 0)
                reasoning = strategy.get("reasoning", "")
                action_steps = strategy.get("action_steps", [])
                risk_warning = strategy.get("risk_warning", "")

                with st.container(border=True):
                    st.subheader(f"策略類型：{strategy_type}")

                    op_cols = st.columns(2)
                    with op_cols[0]:
                        st.markdown(f"**現貨操作：** {spot_action}")
                    with op_cols[1]:
                        st.markdown(f"**期貨操作：** {futures_action}")

                    price_cols = st.columns(4)
                    with price_cols[0]:
                        st.metric("進場價", f"{entry_price:,.1f}")
                    with price_cols[1]:
                        st.metric("停損", f"{stop_loss:,.1f}")
                    with price_cols[2]:
                        st.metric("停利", f"{take_profit:,.1f}")
                    with price_cols[3]:
                        st.metric("風報比", f"{risk_reward:.2f}")

                    if reasoning:
                        st.markdown(f"**分析理由：** {reasoning}")
                    if action_steps:
                        st.markdown("**操作步驟：**")
                        for i, step in enumerate(action_steps, 1):
                            st.markdown(f"{i}. {step}")
                    if risk_warning:
                        st.warning(f"⚠️ {risk_warning}")
            else:
                st.info(f"無法取得 {code} 的對沖分析（HedgeAdvisor 模組尚未建置或無資料）。")

        except Exception as exc:
            logger.warning("個股對沖分析失敗: %s", exc)
            st.warning(f"個股對沖分析失敗：{exc}")

    # ══════════════════════════════════════════
    # 區塊 3：批次掃描（熱門標的）
    # ══════════════════════════════════════════
    st.divider()
    st.header("🔍 熱門標的快速掃描")

    stock_list = st.text_input(
        "掃描清單（逗號分隔）",
        value=", ".join(DEFAULT_STOCKS),
        key="hedge_batch_list",
    )
    scan_clicked = st.button("一鍵掃描", key="hedge_batch_btn", type="primary")

    if scan_clicked and stock_list.strip():
        codes = [c.strip() for c in stock_list.split(",") if c.strip()]
        try:
            with st.spinner(f"掃描 {len(codes)} 檔標的..."):

                @st.cache_data(ttl=300)
                def _batch_scan(_codes: tuple) -> list[dict]:
                    try:
                        from atlas.application.hedge_advisor import HedgeAdvisor

                        advisor = HedgeAdvisor()
                        results = []
                        for _c in _codes:
                            try:
                                r = advisor.analyze_stock(_c, lots=1)
                                strat = r.get("strategy", {})
                                results.append({
                                    "代碼": _c,
                                    "名稱": r.get("name", _c),
                                    "方向": strat.get("direction", "NEUTRAL"),
                                    "信心度": strat.get("confidence", 0),
                                    "策略": strat.get("strategy_type", "—"),
                                    "現貨操作": strat.get("spot_action", "—"),
                                    "期貨操作": strat.get("futures_action", "—"),
                                    "停損": strat.get("stop_loss", 0),
                                    "停利": strat.get("take_profit", 0),
                                })
                            except Exception:
                                results.append({"代碼": _c, "名稱": _c, "方向": "N/A"})
                        return results
                    except ImportError:
                        return []

                scan_results = _batch_scan(tuple(codes))

            if scan_results:
                scan_df = pd.DataFrame(scan_results)
                if "方向" in scan_df.columns:
                    scan_df["方向"] = scan_df["方向"].apply(
                        lambda d: f"{_direction_emoji(d)} {d}" if d != "N/A" else "N/A"
                    )
                st.dataframe(scan_df, hide_index=True, use_container_width=True)
            else:
                st.info("批次掃描無結果（HedgeAdvisor 模組尚未建置）。")

        except Exception as exc:
            logger.warning("批次掃描失敗: %s", exc)
            st.warning(f"批次掃描失敗：{exc}")

    # ══════════════════════════════════════════
    # 區塊 4：風險提示
    # ══════════════════════════════════════════
    st.divider()
    st.caption(
        "⚠️ 免責聲明：本系統僅供參考，不構成投資建議。"
        "期貨交易具有高風險，可能損失超過原始投資金額。"
    )
