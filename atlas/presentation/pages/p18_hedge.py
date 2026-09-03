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

    get_colors()

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
            basis_info = overview.get("basis", {})
            basis_pct = basis_info.get("basis_pct", 0.0) if isinstance(basis_info, dict) else 0.0
            inst_info = overview.get("institutional_futures", {})
            foreign_net = inst_info.get("foreign_net", 0) if isinstance(inst_info, dict) else 0
            pc_ratio = overview.get("put_call_ratio", 0.0)
            direction = overview.get("market_direction", "NEUTRAL")
            market_detail = overview.get("market_detail", "")
            hedge_suggestion = overview.get("hedge_suggestion", "")

            basis_text = f"{'正' if basis_pct > 0 else '逆'}價差 {basis_pct:.2f}%" if basis_pct != 0 else "平水"
            basis_status = "positive" if basis_pct > 0.1 else "negative" if basis_pct < -0.1 else "neutral"
            pc_text, pc_status = _pc_ratio_label(pc_ratio)

            cols = st.columns(4)
            with cols[0]:
                st.markdown(metric_card(
                    "基差狀態", basis_text,
                    status=basis_status,
                ), unsafe_allow_html=True)
            with cols[1]:
                net_status = "positive" if foreign_net > 0 else "negative" if foreign_net < 0 else "neutral"
                st.markdown(metric_card(
                    "外資期貨淨部位", f"{foreign_net:+,} 口",
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
                    "大盤方向", f"{_direction_emoji(direction)} {direction}",
                    status=dir_status,
                ), unsafe_allow_html=True)

            # 大盤分析摘要
            if market_detail:
                st.info(f"📊 {market_detail}")
            if hedge_suggestion:
                st.success(f"💡 {hedge_suggestion}")

            # 三大法人期貨未平倉表格
            try:
                from atlas.infrastructure.taifex_data import fetch_futures_institutional
                inst_df = fetch_futures_institutional()
                if not inst_df.empty:
                    display_df = inst_df.rename(columns={
                        "identity": "法人",
                        "long_volume": "多方交易量",
                        "short_volume": "空方交易量",
                        "long_position": "多方未平倉",
                        "short_position": "空方未平倉",
                        "net_position": "淨部位",
                    })
                    show_cols = [c for c in ["法人", "多方未平倉", "空方未平倉", "淨部位"] if c in display_df.columns]
                    if show_cols:
                        st.dataframe(display_df[show_cols], hide_index=True, width="stretch")
            except Exception:
                pass
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

                from atlas.application.hedge_advisor import HedgeAdvice, HedgeAdvisor

                advisor = HedgeAdvisor()
                adv: HedgeAdvice = advisor.analyze_stock(code, hold_lots)

            # ── 籌碼面指標 ──
            card_cols = st.columns(4)
            with card_cols[0]:
                chg_status = "negative" if adv.margin_change > 500 else "positive" if adv.margin_change < -500 else "neutral"
                st.markdown(metric_card(
                    "融資餘額", f"{adv.margin_balance:,} 張",
                    delta=f"增減 {adv.margin_change:+,}",
                    status=chg_status,
                ), unsafe_allow_html=True)
            with card_cols[1]:
                sr_status = "positive" if adv.short_margin_ratio > 30 else "neutral"
                st.markdown(metric_card(
                    "融券餘額", f"{adv.short_balance:,} 張",
                    delta=f"券資比 {adv.short_margin_ratio:.1f}%",
                    status=sr_status,
                ), unsafe_allow_html=True)
            with card_cols[2]:
                inst_lots = adv.institutional_net // 1000
                inst_status = "positive" if inst_lots > 0 else "negative" if inst_lots < 0 else "neutral"
                st.markdown(metric_card(
                    "法人買賣超", f"{inst_lots:+,} 張",
                    status=inst_status,
                ), unsafe_allow_html=True)
            with card_cols[3]:
                st.markdown(metric_card(
                    "現價", f"{adv.current_price:,.1f}",
                    status="neutral",
                ), unsafe_allow_html=True)

            # ── 方向判定 ──
            dir_cls = _direction_color(adv.direction)
            st.markdown(
                f'<div class="legend-box">'
                f'<strong>方向判定：</strong>'
                f'<span class="{dir_cls}">'
                f'{_direction_emoji(adv.direction)} {adv.direction} — 信心度 {adv.confidence}'
                f'</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── 策略建議卡片 ──
            with st.container(border=True):
                st.subheader(f"策略類型：{adv.hedge_type}")

                op_cols = st.columns(2)
                with op_cols[0]:
                    st.markdown(f"**現貨操作：** {adv.stock_action}")
                with op_cols[1]:
                    st.markdown(f"**期貨操作：** {adv.futures_action}")

                price_cols = st.columns(4)
                with price_cols[0]:
                    st.metric("進場價", f"{adv.entry_price:,.1f}")
                with price_cols[1]:
                    st.metric("停損", f"{adv.stop_loss:,.1f}")
                with price_cols[2]:
                    st.metric("停利", f"{adv.take_profit:,.1f}")
                with price_cols[3]:
                    st.metric("風報比", f"{adv.risk_reward:.2f}")

                if adv.reasoning:
                    st.markdown("**分析理由：**")
                    st.text(adv.reasoning)
                if adv.action_steps:
                    st.markdown("**操作步驟：**")
                    for step in adv.action_steps:
                        st.markdown(f"- {step}")
                if adv.risk_warning:
                    st.warning(f"⚠️ {adv.risk_warning}")

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

                from atlas.application.hedge_advisor import HedgeAdvisor

                advisor = HedgeAdvisor()
                scan_results = []
                for _c in codes:
                    try:
                        adv = advisor.analyze_stock(_c)
                        inst_lots = adv.institutional_net // 1000
                        scan_results.append({
                            "代碼": adv.code,
                            "名稱": adv.name,
                            "現價": adv.current_price,
                            "方向": adv.direction,
                            "信心度": adv.confidence,
                            "策略": adv.hedge_type,
                            "現貨": adv.stock_action,
                            "期貨": adv.futures_action,
                            "法人(張)": f"{inst_lots:+,}",
                            "融資增減": f"{adv.margin_change:+,}",
                            "停損": adv.stop_loss,
                            "停利": adv.take_profit,
                        })
                    except Exception:
                        scan_results.append({"代碼": _c, "名稱": _c, "方向": "N/A"})

            if scan_results:
                scan_df = pd.DataFrame(scan_results)
                if "方向" in scan_df.columns:
                    scan_df["方向"] = scan_df["方向"].apply(
                        lambda d: f"{_direction_emoji(d)} {d}" if d != "N/A" else "N/A"
                    )
                st.dataframe(scan_df, hide_index=True, width="stretch")
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
