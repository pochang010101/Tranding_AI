"""P-02 盤前分析 — 國際行情 + 台指期 + ADR + 資金流向 + 產業題材。"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import bar_chart, gauge_chart
from atlas.presentation.components.theme import get_colors, metric_card, regime_badge
from atlas.presentation.service_container import (
    fetch_stock_data,
    fetch_stock_quote,
    get_indicator_lib,
)

logger = logging.getLogger(__name__)

# 台股重要 ADR
_ADR_TICKERS = [
    ("TSM", "台積電"),
    ("UMC", "聯電"),
    ("ASX", "日月光"),
    ("IMOS", "奇鋐"),
]


def _pct_change(quote: dict) -> float:
    """從 quote dict 計算漲跌%。"""
    price = quote.get("price", 0)
    prev = quote.get("prev_close", 0)
    if not prev:
        return 0.0
    return (price - prev) / prev * 100


def render() -> None:
    st.title("🌏 盤前分析")
    st.markdown("""
<div class="legend-box">
<strong>使用方式</strong>：盤前 08:00~09:00 瀏覽本頁，掌握今日操作方向<br>
<span class="legend-good">國際行情</span>：美股四大指數 + 台指期夜盤，判斷今日台股開盤基調<br>
<span class="legend-warn">ADR 折溢價</span>：台積電等 ADR 隔夜表現，預估權值股方向<br>
<span class="legend-warn">缺口預測</span>：綜合費半 + 台指期 + ADR 估算開盤跳空幅度<br>
&nbsp;&nbsp;• <span class="legend-good">&gt;+0.5%</span> 跳空高開（追多風險高，等拉回）
&nbsp;&nbsp;• <span class="legend-bad">&lt;-0.5%</span> 跳空低開（恐慌殺盤=撿便宜機會）<br>
<span class="legend-good">資金流向</span>：昨日三大法人買賣超金額，判斷籌碼方向<br>
<span class="legend-good">產業題材</span>：熱門題材熱度排行，決定今日聚焦哪些族群<br>
<strong>顏色慣例</strong>：<span class="legend-good">紅色=漲/正面</span>、<span class="legend-bad">綠色=跌/負面</span>（台股標準）
</div>
""", unsafe_allow_html=True)
    get_colors()

    # ══════════════════════════════════════════════
    # Section 1: 美股四大指數 + 台指期夜盤
    # ══════════════════════════════════════════════
    st.subheader("美股四大指數 + 台指期夜盤")
    us_indices = [
        ("道瓊", "^DJI"),
        ("S&P 500", "^GSPC"),
        ("NASDAQ", "^IXIC"),
        ("費半 SOX", "^SOX"),
    ]
    cols = st.columns(5)
    for col, (name, ticker) in zip(cols[:4], us_indices, strict=False):
        with col:
            try:
                q = fetch_stock_quote(ticker)
                price = q["price"]
                chg = _pct_change(q)
                st.markdown(metric_card(
                    name, f"{price:,.0f}", f"{chg:+.2f}%",
                    "positive" if chg > 0 else "negative" if chg < 0 else "neutral",
                ), unsafe_allow_html=True)
            except Exception:
                st.markdown(metric_card(name, "—", status="neutral"),
                            unsafe_allow_html=True)

    # 台指期夜盤（期交所 API）
    with cols[4]:
        try:
            from atlas.infrastructure.twse_bulk import fetch_taifex_futures
            twf = fetch_taifex_futures(session="night")
            if twf and twf.get("close"):
                twf_close = twf["close"]
                twf_change = twf["change"]
                twf_pct = twf_change / (twf_close - twf_change) * 100 if (twf_close - twf_change) else 0
                st.markdown(metric_card(
                    "台指期夜盤", f"{twf_close:,.0f}", f"{twf_pct:+.2f}%",
                    "positive" if twf_change > 0 else "negative" if twf_change < 0 else "neutral",
                ), unsafe_allow_html=True)
            else:
                st.markdown(metric_card("台指期夜盤", "—", status="neutral"),
                            unsafe_allow_html=True)
        except Exception:
            st.markdown(metric_card("台指期夜盤", "—", status="neutral"),
                        unsafe_allow_html=True)

    # ══════════════════════════════════════════════
    # Section 2: ADR 表現 + 缺口預測
    # ══════════════════════════════════════════════
    st.divider()
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("台股 ADR 隔夜表現")
        adr_rows: list[dict] = []
        for ticker, name in _ADR_TICKERS:
            try:
                q = fetch_stock_quote(ticker)
                chg = _pct_change(q)
                adr_rows.append({
                    "代碼": ticker,
                    "名稱": name,
                    "收盤 (USD)": f"{q['price']:.2f}",
                    "漲跌%": round(chg, 2),
                })
            except Exception:
                adr_rows.append({"代碼": ticker, "名稱": name, "收盤 (USD)": "—", "漲跌%": 0.0})

        if adr_rows:
            st.dataframe(
                pd.DataFrame(adr_rows),
                width="stretch", hide_index=True,
                column_config={
                    "漲跌%": st.column_config.NumberColumn(format="%+.2f%%"),
                },
            )

    with col_right:
        st.subheader("缺口預測")
        try:
            from atlas.infrastructure.twse_bulk import fetch_taifex_futures

            sox_q = fetch_stock_quote("^SOX")
            tsm_q = fetch_stock_quote("TSM")
            twf = fetch_taifex_futures(session="night")

            sox_chg = _pct_change(sox_q)
            tsm_chg = _pct_change(tsm_q)
            twf_close = twf.get("close", 0)
            twf_change = twf.get("change", 0)
            twf_chg = twf_change / (twf_close - twf_change) * 100 if (twf_close - twf_change) else 0

            # 加權預估：費半 40% + 台積ADR 30% + 台指期 30%
            gap_est = sox_chg * 0.4 + tsm_chg * 0.3 + twf_chg * 0.3

            if gap_est > 0.5:
                gap_status, gap_text = "positive", "偏多高開"
            elif gap_est < -0.5:
                gap_status, gap_text = "negative", "偏空低開"
            else:
                gap_status, gap_text = "neutral", "平盤附近"

            st.markdown(metric_card("預估缺口", f"{gap_est:+.2f}%", gap_text, gap_status),
                        unsafe_allow_html=True)

            factors = ["費半", "台積ADR", "台指期"]
            factor_vals = [round(sox_chg, 2), round(tsm_chg, 2), round(twf_chg, 2)]
            fig = bar_chart(factors, factor_vals,
                            title="缺口因子漲跌 %", color_by_value=True, height=250)
            st.plotly_chart(fig, width="stretch")
        except Exception:
            st.info("缺口因子資料載入中...")

    # ══════════════════════════════════════════════
    # Section 3: 大盤環境 + 市場情緒
    # ══════════════════════════════════════════════
    st.divider()
    col_env, col_sent = st.columns(2)

    with col_env:
        st.subheader("大盤環境")
        idx_df = fetch_stock_data("^TWII", "3mo")
        if idx_df is not None and not idx_df.empty:
            lib = get_indicator_lib()
            ind = lib.calculate_all(idx_df)
            ma8 = ind["MA8"].iloc[-1] if "MA8" in ind.columns else 0
            ma21 = ind["MA21"].iloc[-1] if "MA21" in ind.columns else 0
            close = idx_df["close"].iloc[-1]

            if ma8 > ma21 and close > ma8:
                st.markdown(regime_badge("BULL"), unsafe_allow_html=True)
                st.markdown(metric_card("趨勢", "多頭排列", status="positive"),
                            unsafe_allow_html=True)
            elif ma8 < ma21 and close < ma8:
                st.markdown(regime_badge("BEAR"), unsafe_allow_html=True)
                st.markdown(metric_card("趨勢", "空頭排列", status="negative"),
                            unsafe_allow_html=True)
            else:
                st.markdown(regime_badge("RANGE"), unsafe_allow_html=True)
                st.markdown(metric_card("趨勢", "盤整", status="neutral"),
                            unsafe_allow_html=True)

            # 成交金額（億元）
            if "volume" in idx_df.columns and len(idx_df) >= 1:
                last_vol = idx_df["volume"].iloc[-1]
                vol_billion = last_vol / 1e8  # 成交金額（億元）
                if vol_billion > 3000:
                    vol_status, vol_hint = "positive", "市場熱絡"
                elif vol_billion > 2000:
                    vol_status, vol_hint = "neutral", "正常水位"
                else:
                    vol_status, vol_hint = "negative", "量能不足"
                st.markdown(metric_card("成交金額", f"{vol_billion:,.0f} 億", vol_hint, vol_status),
                            unsafe_allow_html=True)
        else:
            st.info("台股資料載入中...")

    with col_sent:
        st.subheader("市場情緒")
        if idx_df is not None and not idx_df.empty:
            rsi = ind["RSI14"].iloc[-1] if "RSI14" in ind.columns else 50
            rsi = int(rsi) if rsi == rsi else 50  # NaN guard
            fig = gauge_chart(rsi, title="RSI 情緒指數", height=250)
            st.plotly_chart(fig, width="stretch")

            if rsi >= 70:
                st.warning("⚠️ 極度貪婪區間，留意追高風險")
            elif rsi <= 30:
                st.success("💡 極度恐懼區間，逆勢佈局機會")
            elif rsi >= 60:
                st.info("偏多格局，順勢操作")
            elif rsi <= 40:
                st.info("偏空格局，保守為主")

    # ══════════════════════════════════════════════
    # Section 4: 昨日三大法人資金流向
    # ══════════════════════════════════════════════
    st.divider()
    st.subheader("昨日三大法人資金流向")

    try:
        from atlas.infrastructure.twse_bulk import fetch_twse_institutional

        df_inst = fetch_twse_institutional()
        if not df_inst.empty:
            foreign_total = df_inst["foreign_net"].sum()
            trust_total = df_inst["trust_net"].sum()
            dealer_total = df_inst["dealer_net"].sum()
            total_3inst = foreign_total + trust_total + dealer_total

            # 轉為億元（原始單位：股，用估算均價 50 元計算金額）
            # 更精確：直接除 1e8 當作元→億元近似（法人 net 是股數 × 概念）
            def _to_billion(val: int) -> float:
                return val / 1e4 / 1e4  # 股→萬股→億股，但法人是金額概念... 用張數更直覺

            # 實際上 T86 的 net 單位是「股」，轉張再顯示
            f_lots = foreign_total // 1000
            t_lots = trust_total // 1000
            d_lots = dealer_total // 1000
            total_lots = total_3inst // 1000

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(metric_card(
                    "外資", f"{f_lots:+,.0f} 張", "",
                    "positive" if f_lots > 0 else "negative",
                ), unsafe_allow_html=True)
            with c2:
                st.markdown(metric_card(
                    "投信", f"{t_lots:+,.0f} 張", "",
                    "positive" if t_lots > 0 else "negative",
                ), unsafe_allow_html=True)
            with c3:
                st.markdown(metric_card(
                    "自營商", f"{d_lots:+,.0f} 張", "",
                    "positive" if d_lots > 0 else "negative",
                ), unsafe_allow_html=True)
            with c4:
                st.markdown(metric_card(
                    "合計", f"{total_lots:+,.0f} 張", "",
                    "positive" if total_lots > 0 else "negative",
                ), unsafe_allow_html=True)

            # 外資買超/賣超 Top 5
            col_buy, col_sell = st.columns(2)
            with col_buy:
                st.markdown("**外資買超 Top 5**")
                top_buy = (df_inst.nlargest(5, "foreign_net")
                           [["code", "name", "foreign_net"]]
                           .copy())
                top_buy["foreign_net"] = top_buy["foreign_net"] // 1000
                top_buy.columns = ["代碼", "名稱", "淨買超(張)"]
                st.dataframe(top_buy, width="stretch", hide_index=True)
            with col_sell:
                st.markdown("**外資賣超 Top 5**")
                top_sell = (df_inst.nsmallest(5, "foreign_net")
                            [["code", "name", "foreign_net"]]
                            .copy())
                top_sell["foreign_net"] = top_sell["foreign_net"] // 1000
                top_sell.columns = ["代碼", "名稱", "淨賣超(張)"]
                st.dataframe(top_sell, width="stretch", hide_index=True)
        else:
            st.info("法人資料尚未更新")
    except Exception as exc:
        logger.warning("法人資料載入失敗: %s", exc)
        st.info("法人資料載入中...")

    # ══════════════════════════════════════════════
    # Section 5: 產業題材熱度
    # ══════════════════════════════════════════════
    st.divider()
    st.subheader("產業題材熱度排行")

    try:
        from atlas.infrastructure.twse_bulk import fetch_twse_daily_all
        from atlas.strategy.theme_catalog import detect_hot_themes

        df_daily = fetch_twse_daily_all()
        if not df_daily.empty:
            hot_themes = detect_hot_themes(df_daily, top_n=15)
            if hot_themes:
                theme_rows = []
                for t in hot_themes:
                    if t.heat_score >= 50:
                        heat_label = "🔥 熱門"
                    elif t.heat_score >= 30:
                        heat_label = "📈 溫和"
                    else:
                        heat_label = "➖ 冷門"
                    theme_rows.append({
                        "題材": t.name,
                        "熱度": t.heat_score,
                        "狀態": heat_label,
                        "成分股數": t.stock_count,
                        "上漲比例": f"{t.up_count}/{t.stock_count}",
                        "平均漲幅%": round(t.avg_change_pct, 2),
                        "領漲股": ", ".join(t.top_stocks[:3]) if t.top_stocks else "—",
                    })

                df_themes = pd.DataFrame(theme_rows)
                st.dataframe(
                    df_themes,
                    width="stretch", hide_index=True,
                    column_config={
                        "熱度": st.column_config.ProgressColumn(
                            min_value=0, max_value=100, format="%d",
                        ),
                        "平均漲幅%": st.column_config.NumberColumn(format="%+.2f%%"),
                    },
                )

                # 熱度長條圖
                fig = bar_chart(
                    [t.name for t in hot_themes],
                    [t.heat_score for t in hot_themes],
                    title="題材熱度分數",
                    horizontal=True,
                    color_by_value=False,
                    height=350,
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("無題材熱度資料")
        else:
            st.info("行情資料尚未更新")
    except Exception as exc:
        logger.warning("題材熱度載入失敗: %s", exc)
        st.info("題材資料載入中...")
