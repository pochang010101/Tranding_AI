"""P-12 K 線分析 — 互動式 K 線 + 策略疊加 + 指標切換 + 多時間週期。"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np

from atlas.presentation.components.theme import get_colors
from atlas.presentation.components.charts import candlestick_chart


def _generate_demo_kline(days: int = 240) -> pd.DataFrame:
    """產生 demo K 線資料。"""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(end=pd.Timestamp.now(), periods=days)
    close = 100.0
    rows = []
    for d in dates:
        change = rng.normal(0.001, 0.02)
        o = close
        c = close * (1 + change)
        h = max(o, c) * (1 + abs(rng.normal(0, 0.005)))
        l = min(o, c) * (1 - abs(rng.normal(0, 0.005)))
        v = int(rng.integers(5000, 50000))
        rows.append({"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
        close = c

    df = pd.DataFrame(rows)
    # 計算均線
    for p in [8, 21, 55, 89]:
        df[f"MA{p}"] = df["close"].rolling(p).mean()
    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1 / 14, min_periods=14).mean()
    loss = (-delta).where(delta < 0, 0.0).ewm(alpha=1 / 14, min_periods=14).mean()
    df["RSI14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_hist"] = df["MACD"] - df["MACD_signal"]
    # Bollinger
    df["BB_middle"] = df["close"].rolling(20).mean()
    std = df["close"].rolling(20).std()
    df["BB_upper"] = df["BB_middle"] + 2 * std
    df["BB_lower"] = df["BB_middle"] - 2 * std
    return df


def render() -> None:
    st.title("🕯️ K 線分析")
    c = get_colors()

    # ── 控制列 ──────────────────────────────────
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        code = st.text_input("股票代碼", value="2330", placeholder="輸入代碼")
    with col2:
        timeframe = st.selectbox("時間週期", ["日K", "週K", "月K", "5分K"])
    with col3:
        period = st.selectbox("顯示期間", ["60日", "120日", "240日", "1年", "全部"], index=2)
    with col4:
        if st.button("📊 載入", type="primary", use_container_width=True):
            pass

    # ── 指標選擇 ────────────────────────────────
    st.divider()
    ind_col1, ind_col2, ind_col3 = st.columns(3)
    with ind_col1:
        show_ma = st.multiselect("均線", ["MA8", "MA21", "MA55", "MA89"],
                                  default=["MA8", "MA21", "MA55"])
    with ind_col2:
        overlay = st.multiselect("疊加指標", ["布林通道", "SAR", "Ichimoku"], default=[])
    with ind_col3:
        sub_ind = st.multiselect("副圖指標", ["RSI", "MACD", "KD", "OBV"], default=["RSI", "MACD"])

    # ── K 線主圖 ────────────────────────────────
    days_map = {"60日": 60, "120日": 120, "240日": 240, "1年": 252, "全部": 500}
    n_days = days_map.get(period, 240)
    df = _generate_demo_kline(n_days)

    # 均線週期
    ma_periods = [int(m.replace("MA", "")) for m in show_ma]

    # 訊號標記 demo
    signals = [
        {"date": df["date"].iloc[-50], "type": "BUY", "price": float(df["low"].iloc[-50] * 0.98)},
        {"date": df["date"].iloc[-20], "type": "SELL", "price": float(df["high"].iloc[-20] * 1.02)},
    ]

    fig = candlestick_chart(
        df, ma_periods=ma_periods, volume=True,
        signals=signals, title=f"{code} — {timeframe}",
        height=600,
    )

    # 布林通道疊加
    if "布林通道" in overlay:
        import plotly.graph_objects as go
        for band, dash in [("BB_upper", "dash"), ("BB_middle", "dot"), ("BB_lower", "dash")]:
            if band in df.columns:
                fig.add_trace(go.Scatter(
                    x=df["date"], y=df[band], name=band,
                    line=dict(width=1, dash=dash, color=c["neutral"]),
                ), row=1, col=1)

    st.plotly_chart(fig, use_container_width=True)

    # ── 副圖指標 ────────────────────────────────
    if sub_ind:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        n_sub = len(sub_ind)
        fig_sub = make_subplots(rows=n_sub, cols=1, shared_xaxes=True,
                                vertical_spacing=0.05,
                                row_heights=[1.0 / n_sub] * n_sub)

        for i, ind in enumerate(sub_ind, 1):
            if ind == "RSI" and "RSI14" in df.columns:
                fig_sub.add_trace(go.Scatter(
                    x=df["date"], y=df["RSI14"], name="RSI14",
                    line=dict(color=c["accent"]),
                ), row=i, col=1)
                fig_sub.add_hline(y=70, line_dash="dash", line_color=c["negative"],
                                  opacity=0.5, row=i, col=1)
                fig_sub.add_hline(y=30, line_dash="dash", line_color=c["positive"],
                                  opacity=0.5, row=i, col=1)

            elif ind == "MACD" and "MACD" in df.columns:
                colors_hist = [
                    c["positive"] if v >= 0 else c["negative"]
                    for v in df["MACD_hist"].fillna(0)
                ]
                fig_sub.add_trace(go.Bar(
                    x=df["date"], y=df["MACD_hist"], name="MACD Hist",
                    marker_color=colors_hist, opacity=0.6,
                ), row=i, col=1)
                fig_sub.add_trace(go.Scatter(
                    x=df["date"], y=df["MACD"], name="MACD",
                    line=dict(color=c["accent"], width=1.5),
                ), row=i, col=1)
                fig_sub.add_trace(go.Scatter(
                    x=df["date"], y=df["MACD_signal"], name="Signal",
                    line=dict(color=c["warning"], width=1.5),
                ), row=i, col=1)

            elif ind == "KD":
                # KD demo
                fig_sub.add_trace(go.Scatter(
                    x=df["date"], y=pd.Series(np.random.default_rng(1).uniform(20, 80, len(df))),
                    name="K", line=dict(color=c["accent"]),
                ), row=i, col=1)

            elif ind == "OBV" and "volume" in df.columns:
                obv = (np.sign(df["close"].diff()) * df["volume"]).cumsum()
                fig_sub.add_trace(go.Scatter(
                    x=df["date"], y=obv, name="OBV",
                    line=dict(color=c["accent_secondary"]),
                ), row=i, col=1)

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

    # ── 個股資訊 ────────────────────────────────
    st.divider()
    col_info1, col_info2, col_info3, col_info4 = st.columns(4)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    change_pct = (last["close"] - prev["close"]) / prev["close"] * 100

    with col_info1:
        st.metric("收盤價", f"{last['close']:.2f}",
                  f"{change_pct:+.2f}%")
    with col_info2:
        st.metric("成交量", f"{last['volume']:,}")
    with col_info3:
        rsi_val = last.get("RSI14", 50)
        st.metric("RSI14", f"{rsi_val:.1f}" if not pd.isna(rsi_val) else "N/A")
    with col_info4:
        macd_val = last.get("MACD_hist", 0)
        st.metric("MACD Hist", f"{macd_val:.4f}" if not pd.isna(macd_val) else "N/A")
