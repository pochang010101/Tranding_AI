"""P-02 盤前分析 — 美股收盤、代表股、台指期參考、缺口預測。"""

from __future__ import annotations

import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card, regime_badge
from atlas.presentation.components.charts import bar_chart, gauge_chart
from atlas.presentation.service_container import fetch_stock_quote, fetch_stock_data, get_indicator_lib


def render() -> None:
    st.title("🌏 盤前分析")
    c = get_colors()

    # ── 美股四大指數（即時 yfinance）────────────
    st.subheader("美股四大指數")
    c1, c2, c3, c4 = st.columns(4)
    us_indices = [
        ("道瓊 DJI", "^DJI"),
        ("S&P 500", "^GSPC"),
        ("NASDAQ", "^IXIC"),
        ("費半 SOX", "^SOX"),
    ]
    for col, (name, ticker) in zip([c1, c2, c3, c4], us_indices):
        with col:
            try:
                q = fetch_stock_quote(ticker)
                price = q["price"]
                prev = q["prev_close"]
                chg = (price - prev) / prev * 100 if prev else 0
                st.markdown(metric_card(
                    name, f"{price:,.0f}", f"{chg:+.2f}%",
                    "positive" if chg > 0 else "negative" if chg < 0 else "neutral"
                ), unsafe_allow_html=True)
            except Exception:
                st.markdown(metric_card(name, "—", status="neutral"), unsafe_allow_html=True)

    # ── 代表性美股 ──────────────────────────────
    st.divider()
    st.subheader("8 檔代表性美股")
    us_stocks = [
        ("AAPL", "Apple"), ("NVDA", "NVIDIA"), ("TSM", "台積電ADR"),
        ("MSFT", "Microsoft"), ("GOOGL", "Google"), ("AMZN", "Amazon"),
        ("META", "Meta"), ("AVGO", "Broadcom"),
    ]
    stock_data = {"代碼": [], "名稱": [], "收盤價": [], "漲跌%": []}
    for ticker, name in us_stocks:
        try:
            q = fetch_stock_quote(ticker)
            price = q["price"]
            prev = q["prev_close"]
            chg = (price - prev) / prev * 100 if prev else 0
            stock_data["代碼"].append(ticker)
            stock_data["名稱"].append(name)
            stock_data["收盤價"].append(f"{price:,.1f}")
            stock_data["漲跌%"].append(round(chg, 2))
        except Exception:
            continue

    if stock_data["代碼"]:
        st.dataframe(stock_data, width="stretch", hide_index=True,
                     column_config={"漲跌%": st.column_config.NumberColumn(format="%+.1f%%")})

    # ── 台股指數 + 大盤環境 ──────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("台股加權指數")
        try:
            tw_q = fetch_stock_quote("^TWII")
            tw_price = tw_q["price"]
            tw_prev = tw_q["prev_close"]
            tw_chg = (tw_price - tw_prev) / tw_prev * 100 if tw_prev else 0
            st.markdown(metric_card("加權指數", f"{tw_price:,.0f}",
                        f"{tw_chg:+.2f}%",
                        "positive" if tw_chg > 0 else "negative"),
                        unsafe_allow_html=True)
        except Exception:
            st.markdown(metric_card("加權指數", "—", status="neutral"),
                        unsafe_allow_html=True)

        # 缺口預測因子
        st.subheader("缺口預測因子")
        factors = ["費半指數", "S&P500", "NASDAQ", "台積ADR"]
        try:
            sox_q = fetch_stock_quote("^SOX")
            sp_q = fetch_stock_quote("^GSPC")
            nq_q = fetch_stock_quote("^IXIC")
            tsm_q = fetch_stock_quote("TSM")
            factor_chgs = [
                (sox_q["price"] - sox_q["prev_close"]) / sox_q["prev_close"] * 100 if sox_q["prev_close"] else 0,
                (sp_q["price"] - sp_q["prev_close"]) / sp_q["prev_close"] * 100 if sp_q["prev_close"] else 0,
                (nq_q["price"] - nq_q["prev_close"]) / nq_q["prev_close"] * 100 if nq_q["prev_close"] else 0,
                (tsm_q["price"] - tsm_q["prev_close"]) / tsm_q["prev_close"] * 100 if tsm_q["prev_close"] else 0,
            ]
            fig = bar_chart(factors, [round(v, 2) for v in factor_chgs],
                           title="各因子漲跌幅 %", color_by_value=True, height=300)
            st.plotly_chart(fig, width="stretch")
        except Exception:
            st.info("因子資料載入中...")

    with col_b:
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

            rsi = ind["RSI14"].iloc[-1] if "RSI14" in ind.columns else 50
            rsi = int(rsi) if rsi == rsi else 50
            st.subheader("市場情緒")
            fig = gauge_chart(rsi, title="RSI 情緒指數", height=250)
            st.plotly_chart(fig, width="stretch")
