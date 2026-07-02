"""P-12 K 線分析 — 互動式 K 線 + 策略疊加 + 指標切換 + 多時間週期。"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np

from atlas.presentation.components.theme import get_colors
from atlas.presentation.components.charts import candlestick_chart
from atlas.presentation.service_container import (
    fetch_stock_data,
    get_indicator_lib,
    get_smc_module,
    TW_TOP_STOCKS,
)

# period label → yfinance period string
PERIOD_MAP = {
    "1 個月": "1mo",
    "3 個月": "3mo",
    "6 個月": "6mo",
    "1 年": "1y",
}


def render() -> None:
    st.title("🕯️ K 線分析")
    c = get_colors()

    # ── 股票選擇 ─────────────────────────────────
    stock_labels = [f"{code} {name}" for code, name in TW_TOP_STOCKS]
    col_sel, col_custom = st.columns([3, 2])
    with col_sel:
        selected_label = st.selectbox(
            "熱門股票", options=["（自訂代碼）"] + stock_labels, index=1
        )
    with col_custom:
        if selected_label == "（自訂代碼）":
            custom_code = st.text_input("自訂股票代碼", value="2330", placeholder="e.g. 2330")
            code = custom_code.strip()
        else:
            code = selected_label.split()[0]
            st.text_input("股票代碼（唯讀）", value=code, disabled=True)

    # ── 控制列 ───────────────────────────────────
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        period_label = st.selectbox("顯示期間", list(PERIOD_MAP.keys()), index=2)
    with col2:
        timeframe = st.selectbox("時間週期", ["日K", "週K", "月K"])
    with col3:
        load = st.button("📊 載入", type="primary", use_container_width=True)

    # ── 指標選擇 ─────────────────────────────────
    st.divider()
    ind_col1, ind_col2, ind_col3 = st.columns(3)
    with ind_col1:
        show_ma = st.multiselect(
            "均線", ["MA8", "MA21", "MA55", "MA89"], default=["MA8", "MA21", "MA55"]
        )
    with ind_col2:
        overlay = st.multiselect("疊加指標", ["布林通道", "SMC Order Block"], default=[])
    with ind_col3:
        sub_ind = st.multiselect(
            "副圖指標", ["RSI", "MACD", "KD", "OBV"], default=["RSI", "MACD"]
        )

    # ── 載入資料 ─────────────────────────────────
    period_str = PERIOD_MAP[period_label]

    # 用 session_state 讓「載入」按鈕觸發更新，頁面重渲時保留上次結果
    cache_key = f"p12_{code}_{period_str}"
    if load or cache_key not in st.session_state:
        with st.spinner(f"載入 {code} {period_label} 資料中…"):
            raw_df = fetch_stock_data(code, period_str)
        if raw_df is None or raw_df.empty:
            st.warning(f"⚠️ 無法取得 {code} 的資料，請確認代碼是否正確或網路連線。")
            return
        # 確保 date 欄存在
        raw_df = raw_df.copy()
        raw_df.index = pd.to_datetime(raw_df.index)
        if timeframe == "週K":
            raw_df = raw_df.resample("W-FRI").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            ).dropna()
        elif timeframe == "月K":
            raw_df = raw_df.resample("ME").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            ).dropna()
        raw_df = raw_df.reset_index().rename(columns={"index": "date", "Date": "date", "Datetime": "date"})
        if "date" not in raw_df.columns:
            raw_df.insert(0, "date", raw_df.index)

        # 計算真實技術指標
        try:
            ind_lib = get_indicator_lib()
            df = ind_lib.calculate_all(raw_df)
        except Exception:
            df = raw_df.copy()

        st.session_state[cache_key] = df
    else:
        df = st.session_state[cache_key]

    if df.empty:
        st.warning("資料為空，請換個代碼或期間。")
        return

    # ── SMC 分析 ─────────────────────────────────
    smc_result: dict = {}
    if "SMC Order Block" in overlay:
        try:
            smc_result = get_smc_module().analyze(code, df)
        except Exception as e:
            st.caption(f"SMC 分析略過：{e}")

    # ── K 線主圖 ─────────────────────────────────
    ma_periods = [int(m.replace("MA", "")) for m in show_ma]

    # 從 SMC 結果萃取訊號標記
    signals: list[dict] = []
    if smc_result:
        bias = smc_result.get("bias", "")
        last_row = df.iloc[-1]
        date_col = "date" if "date" in df.columns else df.columns[0]
        if bias in ("BULLISH", "LONG"):
            signals.append({
                "date": last_row[date_col],
                "type": "BUY",
                "price": float(last_row["low"]) * 0.98,
            })
        elif bias in ("BEARISH", "SHORT"):
            signals.append({
                "date": last_row[date_col],
                "type": "SELL",
                "price": float(last_row["high"]) * 1.02,
            })

    fig = candlestick_chart(
        df,
        ma_periods=ma_periods,
        volume=True,
        signals=signals,
        title=f"{code} — {timeframe} ({period_label})",
        height=600,
    )

    # 布林通道疊加
    if "布林通道" in overlay:
        import plotly.graph_objects as go

        date_col = "date" if "date" in df.columns else df.columns[0]
        for band, dash in [("BB_upper", "dash"), ("BB_middle", "dot"), ("BB_lower", "dash")]:
            if band in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df[date_col],
                        y=df[band],
                        name=band,
                        line=dict(width=1, dash=dash, color=c["neutral"]),
                    ),
                    row=1,
                    col=1,
                )

    # SMC Order Block 矩形疊加
    if "SMC Order Block" in overlay and smc_result:
        import plotly.graph_objects as go

        date_col = "date" if "date" in df.columns else df.columns[0]
        x_last = df[date_col].iloc[-1]
        for ob in smc_result.get("order_blocks", [])[:5]:
            color = "rgba(0,200,100,0.15)" if ob.get("type") == "BULL" else "rgba(200,50,50,0.15)"
            fig.add_shape(
                type="rect",
                x0=ob.get("start_date", df[date_col].iloc[0]),
                x1=x_last,
                y0=ob.get("low", 0),
                y1=ob.get("high", 0),
                fillcolor=color,
                line_width=0,
                row=1,
                col=1,
            )

    st.plotly_chart(fig, use_container_width=True)

    # ── 副圖指標 ─────────────────────────────────
    if sub_ind:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        date_col = "date" if "date" in df.columns else df.columns[0]
        n_sub = len(sub_ind)
        fig_sub = make_subplots(
            rows=n_sub,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[1.0 / n_sub] * n_sub,
        )

        for i, ind in enumerate(sub_ind, 1):
            rsi_col = next((col for col in df.columns if col.upper().startswith("RSI")), None)
            if ind == "RSI" and rsi_col:
                fig_sub.add_trace(
                    go.Scatter(
                        x=df[date_col],
                        y=df[rsi_col],
                        name=rsi_col,
                        line=dict(color=c["accent"]),
                    ),
                    row=i,
                    col=1,
                )
                fig_sub.add_hline(y=70, line_dash="dash", line_color=c["negative"], opacity=0.5, row=i, col=1)
                fig_sub.add_hline(y=30, line_dash="dash", line_color=c["positive"], opacity=0.5, row=i, col=1)

            elif ind == "MACD" and "MACD" in df.columns:
                hist_col = "MACD_hist" if "MACD_hist" in df.columns else None
                signal_col = "MACD_signal" if "MACD_signal" in df.columns else None
                if hist_col:
                    colors_hist = [
                        c["positive"] if v >= 0 else c["negative"]
                        for v in df[hist_col].fillna(0)
                    ]
                    fig_sub.add_trace(
                        go.Bar(
                            x=df[date_col],
                            y=df[hist_col],
                            name="MACD Hist",
                            marker_color=colors_hist,
                            opacity=0.6,
                        ),
                        row=i,
                        col=1,
                    )
                fig_sub.add_trace(
                    go.Scatter(
                        x=df[date_col],
                        y=df["MACD"],
                        name="MACD",
                        line=dict(color=c["accent"], width=1.5),
                    ),
                    row=i,
                    col=1,
                )
                if signal_col:
                    fig_sub.add_trace(
                        go.Scatter(
                            x=df[date_col],
                            y=df[signal_col],
                            name="Signal",
                            line=dict(color=c["warning"], width=1.5),
                        ),
                        row=i,
                        col=1,
                    )

            elif ind == "KD":
                k_col = next((col for col in df.columns if col.upper() == "K" or col.upper() == "STOCH_K"), None)
                d_col = next((col for col in df.columns if col.upper() == "D" or col.upper() == "STOCH_D"), None)
                if k_col and d_col:
                    fig_sub.add_trace(
                        go.Scatter(x=df[date_col], y=df[k_col], name="K", line=dict(color=c["accent"])),
                        row=i, col=1,
                    )
                    fig_sub.add_trace(
                        go.Scatter(x=df[date_col], y=df[d_col], name="D", line=dict(color=c["warning"])),
                        row=i, col=1,
                    )
                else:
                    st.caption("KD 欄位不在指標結果中，略過。")

            elif ind == "OBV":
                obv_col = next((col for col in df.columns if col.upper() == "OBV"), None)
                if obv_col:
                    fig_sub.add_trace(
                        go.Scatter(
                            x=df[date_col],
                            y=df[obv_col],
                            name="OBV",
                            line=dict(color=c["accent_secondary"]),
                        ),
                        row=i,
                        col=1,
                    )
                elif "volume" in df.columns:
                    # fallback: 從 close/volume 自算
                    obv = (np.sign(df["close"].diff()) * df["volume"]).cumsum()
                    fig_sub.add_trace(
                        go.Scatter(
                            x=df[date_col], y=obv, name="OBV",
                            line=dict(color=c["accent_secondary"]),
                        ),
                        row=i, col=1,
                    )

        fig_sub.update_layout(
            template=c["plotly_template"],
            plot_bgcolor=c["plotly_bg"],
            paper_bgcolor=c["plotly_paper"],
            font=dict(color=c["text_primary"]),
            height=200 * n_sub,
            margin=dict(l=50, r=30, t=10, b=30),
            showlegend=True,
        )
        st.plotly_chart(fig_sub, use_container_width=True)

    # ── 個股資訊卡 ───────────────────────────────
    st.divider()
    col_info1, col_info2, col_info3, col_info4 = st.columns(4)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    change_pct = (last["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0

    with col_info1:
        st.metric("收盤價", f"{last['close']:.2f}", f"{change_pct:+.2f}%")
    with col_info2:
        vol_val = last.get("volume", 0)
        st.metric("成交量", f"{int(vol_val):,}" if not pd.isna(vol_val) else "N/A")
    with col_info3:
        rsi_col = next((col for col in df.columns if col.upper().startswith("RSI")), None)
        rsi_val = last.get(rsi_col, float("nan")) if rsi_col else float("nan")
        st.metric("RSI14", f"{rsi_val:.1f}" if not pd.isna(rsi_val) else "N/A")
    with col_info4:
        hist_val = last.get("MACD_hist", float("nan"))
        st.metric("MACD Hist", f"{hist_val:.4f}" if not pd.isna(hist_val) else "N/A")

    # SMC 偏向摘要
    if smc_result:
        bias = smc_result.get("bias", "NEUTRAL")
        bias_color = {"BULLISH": "green", "LONG": "green", "BEARISH": "red", "SHORT": "red"}.get(bias, "gray")
        st.markdown(
            f"**SMC 偏向**：<span style='color:{bias_color}; font-weight:bold'>{bias}</span>",
            unsafe_allow_html=True,
        )
