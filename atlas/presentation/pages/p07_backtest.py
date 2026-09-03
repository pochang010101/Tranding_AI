"""P-07 回測分析 — 真實 OHLCV 資料回測，支援多股比較與買賣點標記。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import (
    bar_chart,
    candlestick_chart,
    equity_curve,
    histogram,
)
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    TW_TOP_STOCKS,
    fetch_stock_data,
    get_indicator_lib,
    get_monte_carlo,
)

# ── 策略定義 ──────────────────────────────────────────────────────────────────
_STRATEGIES: dict[str, str] = {
    "ma_cross": "MA 交叉（MA8 上穿 MA21 買入，下穿賣出）",
    "rsi_revert": "RSI 超賣反彈（RSI < 30 買入，> 70 賣出）",
    "macd_cross": "MACD 金叉（Histogram 由負轉正買入，由正轉負賣出）",
    "granville": "葛蘭碧買點（均線支撐買入法）",
    "institutional": "法人同步（外資+投信同方向買超 3 天買入，轉賣出場）",
}

_PERIOD_MAP: dict[str, str] = {
    "3個月": "3mo",
    "6個月": "6mo",
    "1年": "1y",
    "2年": "2y",
}


# ── 訊號產生 ─────────────────────────────────────────────────────────────────

def _generate_signals(df: pd.DataFrame, strategy: str) -> pd.Series:
    """根據策略產生買賣訊號 Series（1=買, -1=賣, 0=無動作）。"""
    signals = pd.Series(0, index=df.index)

    if strategy == "ma_cross":
        if "MA8" not in df.columns or "MA21" not in df.columns:
            return signals
        ma8 = df["MA8"]
        ma21 = df["MA21"]
        signals[(ma8 > ma21) & (ma8.shift(1) <= ma21.shift(1))] = 1
        signals[(ma8 < ma21) & (ma8.shift(1) >= ma21.shift(1))] = -1

    elif strategy == "rsi_revert":
        if "RSI14" not in df.columns:
            return signals
        rsi = df["RSI14"]
        signals[(rsi < 30) & (rsi.shift(1) >= 30)] = 1
        signals[(rsi > 70) & (rsi.shift(1) <= 70)] = -1

    elif strategy == "macd_cross":
        if "MACD_hist" not in df.columns:
            return signals
        hist = df["MACD_hist"]
        signals[(hist > 0) & (hist.shift(1) <= 0)] = 1
        signals[(hist < 0) & (hist.shift(1) >= 0)] = -1

    elif strategy == "granville":
        # 葛蘭碧買點：價格回測 MA21 支撐後反彈
        if "MA21" not in df.columns:
            return signals
        close = df["close"]
        ma21 = df["MA21"]
        # 買：MA21 向上 + 收盤跌近 MA21(±2%) 後隔日反彈
        ma21_up = ma21 > ma21.shift(1)
        near_ma = (close.shift(1) / ma21.shift(1) - 1).abs() < 0.02
        bounce = close > close.shift(1)
        signals[ma21_up & near_ma & bounce] = 1
        # 賣：跌破 MA21 且 MA21 走平或向下
        ma21_flat_down = ma21 <= ma21.shift(1)
        below_ma = close < ma21
        signals[ma21_flat_down & below_ma & ~below_ma.shift(1).fillna(False)] = -1

    elif strategy == "institutional":
        # 法人同步：placeholder — 在回測迴圈中由外部注入
        # 此處回傳空訊號，實際由 _run_institutional_backtest 處理
        pass

    return signals


def _run_simple_backtest(
    code: str,
    ohlcv_df: pd.DataFrame,
    strategy: str,
    initial_capital: float,
    fee_rate: float,
    tax_rate: float,
) -> dict[str, Any]:
    """簡易回測引擎（同步，不依賴 DB）。回傳績效字典。"""
    lib = get_indicator_lib()
    df = lib.calculate_all(ohlcv_df)

    if len(df) < 30:
        return {"error": f"{code} 資料不足 30 根 K 棒，跳過。"}

    signals = _generate_signals(df, strategy)

    # 模擬交易
    trades: list[dict[str, Any]] = []
    position = 0
    entry_price = 0.0
    capital = initial_capital
    equity_list: list[float] = []

    for idx in range(len(df)):
        row = df.iloc[idx]
        sig = signals.iloc[idx]
        dt = df.index[idx]

        if sig == 1 and position == 0:
            # 買入：用 95% 資金，整張(1000股)
            max_shares = int(capital * 0.95 / row["close"] / 1000) * 1000
            if max_shares >= 1000:
                cost = max_shares * row["close"] * (1 + fee_rate / 100)
                capital -= cost
                position = max_shares
                entry_price = row["close"]
                trades.append({
                    "日期": str(dt.date()) if hasattr(dt, "date") else str(dt),
                    "動作": "買入",
                    "價格": round(row["close"], 2),
                    "股數": max_shares,
                    "損益": 0.0,
                })

        elif sig == -1 and position > 0:
            # 賣出
            revenue = position * row["close"] * (1 - fee_rate / 100 - tax_rate / 100)
            pnl = revenue - position * entry_price * (1 + fee_rate / 100)
            capital += revenue
            trades.append({
                "日期": str(dt.date()) if hasattr(dt, "date") else str(dt),
                "動作": "賣出",
                "價格": round(row["close"], 2),
                "股數": position,
                "損益": round(pnl, 0),
            })
            position = 0

        # 每日淨值
        market_value = capital + position * row["close"]
        equity_list.append(market_value)

    # 期末若仍有持倉，以最後收盤價計算
    final_close = df["close"].iloc[-1]
    final_value = capital + position * final_close

    # 績效計算
    total_return = (final_value / initial_capital - 1) * 100

    # 勝率（只算配對交易）
    sell_trades = [t for t in trades if t["動作"] == "賣出"]
    win_count = sum(1 for t in sell_trades if t["損益"] > 0)
    win_rate = (win_count / len(sell_trades) * 100) if sell_trades else 0.0

    # 最大回撤
    if equity_list:
        eq_arr = np.array(equity_list)
        peak = np.maximum.accumulate(eq_arr)
        dd = (peak - eq_arr) / peak
        max_drawdown = float(np.max(dd)) * 100
    else:
        max_drawdown = 0.0

    # Sharpe Ratio
    if len(equity_list) > 1:
        eq_series = pd.Series(equity_list)
        daily_ret = eq_series.pct_change().dropna()
        if daily_ret.std() > 0:
            sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252))
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    # 年化報酬
    n_days = len(df)
    annual_return = total_return * (252 / n_days) if n_days > 0 else 0.0

    # 買賣點標記（供 K 線圖用）
    buy_sell_markers: list[dict[str, Any]] = []
    for t in trades:
        buy_sell_markers.append({
            "date": t["日期"],
            "type": "BUY" if t["動作"] == "買入" else "SELL",
            "price": t["價格"],
        })

    return {
        "code": code,
        "trades": trades,
        "equity_curve": equity_list,
        "total_return": round(total_return, 2),
        "annual_return": round(annual_return, 2),
        "win_rate": round(win_rate, 2),
        "max_drawdown": round(max_drawdown, 2),
        "sharpe_ratio": round(sharpe, 2),
        "trade_count": len(sell_trades),
        "final_value": round(final_value, 0),
        "markers": buy_sell_markers,
        "df": df,  # 含指標的 DataFrame，用於 K 線圖
    }


def _run_institutional_backtest(
    code: str,
    ohlcv_df: pd.DataFrame,
    initial_capital: float,
    fee_rate: float,
    tax_rate: float,
) -> dict[str, Any]:
    """法人同步策略回測：用 fetch_institutional_flow 取得法人資料。

    注意：法人資料僅有近期單日，無法回溯歷史。
    此處改用簡化版：MA8 > MA21 且成交量 > 5 日均量作為法人進場替代。
    """
    lib = get_indicator_lib()
    df = lib.calculate_all(ohlcv_df)

    if len(df) < 30:
        return {"error": f"{code} 資料不足 30 根 K 棒，跳過。"}

    # 簡化法人同步：量能放大 + 短均上穿長均 = 法人進場訊號
    signals = pd.Series(0, index=df.index)
    if "MA8" in df.columns and "MA21" in df.columns and "volume" in df.columns:
        vol_surge = df["volume"] > df["volume"].rolling(5).mean() * 1.3
        ma_up = (df["MA8"] > df["MA21"]) & (df["MA8"].shift(1) <= df["MA21"].shift(1))
        ma_dn = (df["MA8"] < df["MA21"]) & (df["MA8"].shift(1) >= df["MA21"].shift(1))
        signals[ma_up & vol_surge] = 1
        signals[ma_dn] = -1

    # 複用 simple backtest 邏輯
    trades: list[dict[str, Any]] = []
    position = 0
    entry_price = 0.0
    capital = initial_capital
    equity_list: list[float] = []

    for idx in range(len(df)):
        row = df.iloc[idx]
        sig = signals.iloc[idx]
        dt = df.index[idx]

        if sig == 1 and position == 0:
            max_shares = int(capital * 0.95 / row["close"] / 1000) * 1000
            if max_shares >= 1000:
                cost = max_shares * row["close"] * (1 + fee_rate / 100)
                capital -= cost
                position = max_shares
                entry_price = row["close"]
                trades.append({
                    "日期": str(dt.date()) if hasattr(dt, "date") else str(dt),
                    "動作": "買入",
                    "價格": round(row["close"], 2),
                    "股數": max_shares,
                    "損益": 0.0,
                })
        elif sig == -1 and position > 0:
            revenue = position * row["close"] * (1 - fee_rate / 100 - tax_rate / 100)
            pnl = revenue - position * entry_price * (1 + fee_rate / 100)
            capital += revenue
            trades.append({
                "日期": str(dt.date()) if hasattr(dt, "date") else str(dt),
                "動作": "賣出",
                "價格": round(row["close"], 2),
                "股數": position,
                "損益": round(pnl, 0),
            })
            position = 0

        market_value = capital + position * row["close"]
        equity_list.append(market_value)

    final_close = df["close"].iloc[-1]
    final_value = capital + position * final_close
    total_return = (final_value / initial_capital - 1) * 100

    sell_trades = [t for t in trades if t["動作"] == "賣出"]
    win_count = sum(1 for t in sell_trades if t["損益"] > 0)
    win_rate = (win_count / len(sell_trades) * 100) if sell_trades else 0.0

    if equity_list:
        eq_arr = np.array(equity_list)
        peak = np.maximum.accumulate(eq_arr)
        dd = (peak - eq_arr) / peak
        max_drawdown = float(np.max(dd)) * 100
    else:
        max_drawdown = 0.0

    if len(equity_list) > 1:
        eq_series = pd.Series(equity_list)
        daily_ret = eq_series.pct_change().dropna()
        sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0.0
    else:
        sharpe = 0.0

    n_days = len(df)
    annual_return = total_return * (252 / n_days) if n_days > 0 else 0.0

    buy_sell_markers: list[dict[str, Any]] = []
    for t in trades:
        buy_sell_markers.append({
            "date": t["日期"],
            "type": "BUY" if t["動作"] == "買入" else "SELL",
            "price": t["價格"],
        })

    return {
        "code": code,
        "trades": trades,
        "equity_curve": equity_list,
        "total_return": round(total_return, 2),
        "annual_return": round(annual_return, 2),
        "win_rate": round(win_rate, 2),
        "max_drawdown": round(max_drawdown, 2),
        "sharpe_ratio": round(sharpe, 2),
        "trade_count": len(sell_trades),
        "final_value": round(final_value, 0),
        "markers": buy_sell_markers,
        "df": df,
    }


# ── 頁面 ─────────────────────────────────────────────────────────────────────

def render() -> None:
    st.title("回測分析")
    st.markdown("""
<div class="legend-box">
<strong>使用說明</strong><br>
選擇股票與策略後按「開始回測」，系統會用真實歷史資料模擬交易。<br>
<b>總報酬</b>：回測期間累計報酬率｜
<b>勝率</b>：獲利交易佔比，&gt;50% 為正｜
<b>最大回撤</b>：歷史最大虧損幅度，&lt;-20% 風險高｜
<b>Sharpe Ratio</b>：風險調整後報酬，&gt;1.0 良好、&gt;2.0 優秀｜
交易以「張」(1000股) 為單位，手續費/交易稅依台股標準。
</div>
""", unsafe_allow_html=True)
    get_colors()

    # ── 區塊 1：回測設定 ──────────────────────────
    with st.expander("回測設定", expanded=True):
        col_stock, col_strategy = st.columns(2)

        with col_stock:
            stock_options = [f"{c} {n}" for c, n in TW_TOP_STOCKS]
            selected_stocks = st.multiselect(
                "選擇股票（可多選）",
                options=stock_options,
                default=[stock_options[0]],
                help="從 TW Top 30 選擇，或在下方自訂代碼",
            )
            custom_codes = st.text_input(
                "自訂股票代碼（逗號分隔）",
                placeholder="例：3037, 2345, 6547",
                help="輸入台股代碼，會與上方選擇合併",
            )

        with col_strategy:
            strategy = st.radio(
                "策略選擇",
                options=list(_STRATEGIES.keys()),
                format_func=lambda k: _STRATEGIES[k],
                index=0,
            )

        col_period, col_capital, col_fee, col_tax = st.columns(4)
        with col_period:
            period_label = st.selectbox("回測期間", list(_PERIOD_MAP.keys()), index=1)
        with col_capital:
            capital = st.number_input(
                "初始資金 (TWD)", value=1_000_000, step=100_000, min_value=100_000, format="%d",
            )
        with col_fee:
            fee_rate = st.number_input(
                "手續費率 (%)", value=0.1425, step=0.01, min_value=0.0, format="%.4f",
            )
        with col_tax:
            tax_rate = st.number_input(
                "交易稅率 (%)", value=0.3000, step=0.01, min_value=0.0, format="%.4f",
            )

        run_clicked = st.button("開始回測", type="primary", use_container_width=True)

    # 解析選擇的股票代碼
    codes: list[str] = []
    for s in selected_stocks:
        codes.append(s.split(" ")[0])
    if custom_codes.strip():
        for c in custom_codes.split(","):
            c = c.strip()
            if c and c not in codes:
                codes.append(c)

    # ── 區塊 2：執行回測 ──────────────────────────
    if run_clicked:
        if not codes:
            st.warning("請至少選擇一檔股票。")
            return

        period = _PERIOD_MAP[period_label]
        results: list[dict[str, Any]] = []
        progress = st.progress(0, text="抓取股票資料中...")

        for idx, code in enumerate(codes):
            progress.progress(
                (idx + 1) / len(codes),
                text=f"回測 {code} ({idx + 1}/{len(codes)})",
            )
            try:
                ohlcv = fetch_stock_data(code, period=period)
                if ohlcv is None or ohlcv.empty:
                    st.warning(f"{code} 無法取得資料，跳過。")
                    continue

                if strategy == "institutional":
                    res = _run_institutional_backtest(
                        code, ohlcv, float(capital), fee_rate, tax_rate,
                    )
                else:
                    res = _run_simple_backtest(
                        code, ohlcv, strategy, float(capital), fee_rate, tax_rate,
                    )

                if "error" not in res:
                    results.append(res)
                else:
                    st.warning(res["error"])
            except Exception as e:
                st.warning(f"{code} 回測失敗：{e}")

        progress.empty()

        if results:
            st.session_state["bt_results"] = results
            total_trades = sum(r["trade_count"] for r in results)
            st.success(f"回測完成！共 {len(results)} 檔股票、{total_trades} 筆完整交易。")
        else:
            st.warning("回測期間無任何交易訊號，請更換策略或延長期間。")
            return

    # ── 區塊 3：回測結果 ──────────────────────────
    bt_results: list[dict] | None = st.session_state.get("bt_results")

    if not bt_results:
        st.info("請設定參數後按「開始回測」。")
        return

    st.divider()

    # 如果只有一檔，顯示詳細結果
    if len(bt_results) == 1:
        _render_single_result(bt_results[0], float(capital))
    else:
        # 多檔：先顯示比較表，再逐檔顯示
        _render_multi_comparison(bt_results)

        st.divider()
        for res in bt_results:
            with st.expander(f"{res['code']} 詳細結果", expanded=False):
                _render_single_result(res, float(capital))


def _render_single_result(res: dict[str, Any], capital: float) -> None:
    """渲染單檔股票的回測結果。"""

    def _sign(v: float) -> str:
        return "positive" if v >= 0 else "negative"

    # ── 績效指標卡片 ──────────────────────────
    st.subheader(f"{res['code']} 回測績效")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            metric_card("總報酬", f"{res['total_return']:+.2f}%", status=_sign(res["total_return"])),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            metric_card("勝率", f"{res['win_rate']:.1f}%", status=_sign(res["win_rate"] - 50)),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            metric_card("最大回撤", f"-{res['max_drawdown']:.2f}%", status="negative"),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            metric_card("Sharpe", f"{res['sharpe_ratio']:.2f}", status=_sign(res["sharpe_ratio"])),
            unsafe_allow_html=True,
        )

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.metric("年化報酬", f"{res['annual_return']:+.2f}%")
    with c6:
        st.metric("完整交易數", f"{res['trade_count']}")
    with c7:
        st.metric("期末資產", f"${res['final_value']:,.0f}")
    with c8:
        pnl = res["final_value"] - capital
        st.metric("累計損益", f"${pnl:+,.0f}")

    # ── 淨值曲線 ──────────────────────────────
    eq_data = res.get("equity_curve", [])
    if eq_data:
        fig = equity_curve(eq_data, title=f"{res['code']} 淨值曲線 + 回撤", height=450)
        st.plotly_chart(fig, use_container_width=True)

    # ── K 線圖 + 買賣點標記 ───────────────────
    tab_k, tab_trades, tab_r, tab_mc = st.tabs(
        ["K線買賣點", "交易明細", "R 倍數分佈", "蒙地卡羅"]
    )

    with tab_k:
        df_plot = res.get("df")
        markers = res.get("markers", [])
        if df_plot is not None and not df_plot.empty:
            try:
                fig_k = candlestick_chart(
                    df_plot,
                    ma_periods=[8, 21],
                    volume=True,
                    signals=markers,
                    title=f"{res['code']} K 線 + 買賣點標記",
                    height=650,
                )
                st.plotly_chart(fig_k, use_container_width=True)
            except Exception as e:
                st.warning(f"K 線圖繪製失敗：{e}")
        else:
            st.info("無 K 線資料。")

    with tab_trades:
        trades = res.get("trades", [])
        if trades:
            trades_df = pd.DataFrame(trades)
            st.dataframe(
                trades_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "損益": st.column_config.NumberColumn(format="%,.0f"),
                    "價格": st.column_config.NumberColumn(format="%.2f"),
                },
            )
        else:
            st.info("無交易紀錄。")

    with tab_r:
        sell_trades = [t for t in res.get("trades", []) if t["動作"] == "賣出"]
        if sell_trades:
            pnls = [t["損益"] for t in sell_trades]
            avg_loss = abs(np.mean([p for p in pnls if p <= 0])) if any(p <= 0 for p in pnls) else 1.0
            r_values = [p / avg_loss for p in pnls]
            fig_r = histogram(r_values, title="R 倍數分佈", x_label="R 倍數", bins=25, height=400)
            st.plotly_chart(fig_r, use_container_width=True)

            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                st.metric("平均 R", f"{np.mean(r_values):.2f}")
            with rc2:
                st.metric("中位數 R", f"{np.median(r_values):.2f}")
            with rc3:
                wr_frac = res["win_rate"] / 100
                st.metric("期望值 (EV)", f"{np.mean(r_values) * wr_frac:.2f}")
        else:
            st.info("無交易紀錄。")

    with tab_mc:
        _render_monte_carlo(res.get("trades", []), capital, key_suffix=res["code"])


def _render_multi_comparison(results: list[dict[str, Any]]) -> None:
    """多股回測比較：摘要表 + 報酬率柱狀圖。"""
    st.subheader("多股回測比較")

    # 摘要表
    summary_rows = []
    for r in results:
        summary_rows.append({
            "股票代碼": r["code"],
            "總報酬%": r["total_return"],
            "年化報酬%": r["annual_return"],
            "勝率%": r["win_rate"],
            "最大回撤%": r["max_drawdown"],
            "Sharpe": r["sharpe_ratio"],
            "交易數": r["trade_count"],
            "期末資產": r["final_value"],
        })

    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(
        summary_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "總報酬%": st.column_config.NumberColumn(format="%+.2f%%"),
            "年化報酬%": st.column_config.NumberColumn(format="%+.2f%%"),
            "勝率%": st.column_config.NumberColumn(format="%.1f%%"),
            "最大回撤%": st.column_config.NumberColumn(format="%.2f%%"),
            "Sharpe": st.column_config.NumberColumn(format="%.2f"),
            "期末資產": st.column_config.NumberColumn(format="%,.0f"),
        },
    )

    # 報酬率柱狀圖
    labels = [r["code"] for r in results]
    values = [r["total_return"] for r in results]
    fig = bar_chart(
        labels, values,
        title="各股回測報酬率比較 (%)",
        color_by_value=True,
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)

    # 將正報酬股票寫入 session_state，供 P-13 紙上交易接收
    positive = [r["code"] for r in results if r["total_return"] > 0]
    if positive:
        st.session_state["backtest_recommended"] = positive
        st.success(
            f"已將 {len(positive)} 檔正報酬股票推薦至紙上交易（P-13）：{', '.join(positive)}"
        )
        if st.button("前往紙上交易建倉 →", key="go_paper"):
            st.session_state["page"] = "paper"
            st.rerun()


def _render_monte_carlo(
    trades: list[dict], capital: float, key_suffix: str = "",
) -> None:
    """蒙地卡羅模擬區塊。"""
    st.subheader("蒙地卡羅模擬")
    mc_col1, mc_col2 = st.columns([1, 2])

    with mc_col1:
        mc_paths = st.slider(
            "模擬路徑數", 100, 5000, 1000, 100, key=f"mc_paths_{key_suffix}",
        )
        mc_run = st.button("執行模擬", use_container_width=True, key=f"mc_run_{key_suffix}")

    sell_trades = [t for t in trades if t.get("動作") == "賣出"]

    if mc_run:
        if not sell_trades:
            st.warning("請先執行回測取得交易紀錄再進行蒙地卡羅模擬。")
            return

        pnl_list = [t["損益"] for t in sell_trades]
        with st.spinner("蒙地卡羅模擬中..."):
            mc_result = get_monte_carlo().simulate(
                trades=pnl_list,
                num_paths=mc_paths,
                initial_capital=capital,
            )
        st.session_state[f"mc_result_{key_suffix}"] = mc_result

    mc_result = st.session_state.get(f"mc_result_{key_suffix}")

    with mc_col2:
        if mc_result is not None:
            finals_approx = np.interp(
                np.linspace(0, 100, 1000),
                [5, 25, 50, 75, 95],
                [
                    mc_result.percentile_5, mc_result.percentile_25,
                    mc_result.percentile_50, mc_result.percentile_75,
                    mc_result.percentile_95,
                ],
            )
            fig = histogram(
                list(finals_approx),
                title="最終資金分佈（近似）",
                x_label="最終資金",
                bins=40,
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("請按「執行模擬」開始蒙地卡羅分析。")

    if mc_result is not None:
        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.metric("P5（悲觀）", f"${mc_result.percentile_5:,.0f}")
        with mc2:
            st.metric("P50（中位）", f"${mc_result.percentile_50:,.0f}")
        with mc3:
            st.metric("P95（樂觀）", f"${mc_result.percentile_95:,.0f}")
        with mc4:
            st.metric("破產機率", f"{mc_result.ruin_probability * 100:.1f}%")
