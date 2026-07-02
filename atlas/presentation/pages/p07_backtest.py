"""P-07 回測分析 — 策略選擇、參數設定、回測結果、參數掃描、蒙地卡羅。"""

from __future__ import annotations

import datetime
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import equity_curve, histogram
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    TW_TOP_STOCKS,
    fetch_stock_data,
    get_indicator_lib,
    get_monte_carlo,
)

# ── 策略定義 ──────────────────────────────────────────────────────────────────
_STRATEGIES: dict[str, str] = {
    "S1_均線突破": "MA 快線(8)上穿慢線(21) 做多，下穿平倉",
    "S2_量價齊揚": "MACD 金叉且成交量 > 5日均量 做多",
    "O1_跳空": "當日開盤跳空向上 > 0.5% 做多",
    "K1_扣抵翻揚": "MA21 扣抵值由負轉正做多",
    "P1_W底": "RSI < 35 後 RSI 上穿 45 做多",
    "T1_RSI反轉": "RSI < 30 做多，RSI > 70 平倉",
    "SD1_空頭反轉": "MACD 死叉做空，金叉平倉",
}

_DEFAULT_COST_RATE = 0.00685  # 手續費 + 證交稅 + 滑價


# ── 訊號生成 ─────────────────────────────────────────────────────────────────

def _generate_signals(code: str, df: pd.DataFrame, strategy: str) -> list[dict[str, Any]]:
    """從指標 DataFrame 產生 BUY/SELL 訊號列表。

    Returns list of {"code", "date", "direction": "BUY"/"SELL", "price"}.
    """
    if df.empty or len(df) < 30:
        return []

    close = df["close"]
    signals: list[dict] = []

    if strategy == "S1_均線突破":
        if "MA8" not in df.columns or "MA21" not in df.columns:
            return []
        fast, slow = df["MA8"], df["MA21"]
        cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        cross_dn = (fast < slow) & (fast.shift(1) >= slow.shift(1))
        for i in df.index[cross_up]:
            signals.append({"code": code, "date": i, "direction": "BUY", "price": float(close.loc[i])})
        for i in df.index[cross_dn]:
            signals.append({"code": code, "date": i, "direction": "SELL", "price": float(close.loc[i])})

    elif strategy == "S2_量價齊揚":
        if "MACD" not in df.columns or "MACD_signal" not in df.columns or "volume" not in df.columns:
            return []
        macd_cross_up = (df["MACD"] > df["MACD_signal"]) & (df["MACD"].shift(1) <= df["MACD_signal"].shift(1))
        macd_cross_dn = (df["MACD"] < df["MACD_signal"]) & (df["MACD"].shift(1) >= df["MACD_signal"].shift(1))
        vol_ok = df["volume"] > df["volume"].rolling(5).mean()
        for i in df.index[macd_cross_up & vol_ok]:
            signals.append({"code": code, "date": i, "direction": "BUY", "price": float(close.loc[i])})
        for i in df.index[macd_cross_dn]:
            signals.append({"code": code, "date": i, "direction": "SELL", "price": float(close.loc[i])})

    elif strategy == "O1_跳空":
        if "open" not in df.columns:
            return []
        gap_up = (df["open"] / close.shift(1) - 1) > 0.005
        gap_dn = (df["open"] / close.shift(1) - 1) < -0.005
        for i in df.index[gap_up]:
            signals.append({"code": code, "date": i, "direction": "BUY", "price": float(df["open"].loc[i])})
        for i in df.index[gap_dn]:
            signals.append({"code": code, "date": i, "direction": "SELL", "price": float(close.loc[i])})

    elif strategy == "K1_扣抵翻揚":
        if "MA21" not in df.columns:
            return []
        ind = get_indicator_lib()
        offset = ind.deduction_offset(close, 21)
        turn_up = (offset > 0) & (offset.shift(1) <= 0)
        turn_dn = (offset < 0) & (offset.shift(1) >= 0)
        for i in df.index[turn_up]:
            signals.append({"code": code, "date": i, "direction": "BUY", "price": float(close.loc[i])})
        for i in df.index[turn_dn]:
            signals.append({"code": code, "date": i, "direction": "SELL", "price": float(close.loc[i])})

    elif strategy == "P1_W底":
        if "RSI14" not in df.columns:
            return []
        rsi = df["RSI14"]
        was_low = rsi.shift(1) < 35
        cross_45 = (rsi > 45) & (rsi.shift(1) <= 45)
        overbought = rsi > 70
        for i in df.index[was_low & cross_45]:
            signals.append({"code": code, "date": i, "direction": "BUY", "price": float(close.loc[i])})
        for i in df.index[overbought & ~overbought.shift(1).fillna(False)]:
            signals.append({"code": code, "date": i, "direction": "SELL", "price": float(close.loc[i])})

    elif strategy == "T1_RSI反轉":
        if "RSI14" not in df.columns:
            return []
        rsi = df["RSI14"]
        buy_sig = (rsi < 30) & (rsi.shift(1) >= 30)
        sell_sig = (rsi > 70) & (rsi.shift(1) <= 70)
        for i in df.index[buy_sig]:
            signals.append({"code": code, "date": i, "direction": "BUY", "price": float(close.loc[i])})
        for i in df.index[sell_sig]:
            signals.append({"code": code, "date": i, "direction": "SELL", "price": float(close.loc[i])})

    elif strategy == "SD1_空頭反轉":
        if "MACD" not in df.columns or "MACD_signal" not in df.columns:
            return []
        cross_dn = (df["MACD"] < df["MACD_signal"]) & (df["MACD"].shift(1) >= df["MACD_signal"].shift(1))
        cross_up = (df["MACD"] > df["MACD_signal"]) & (df["MACD"].shift(1) <= df["MACD_signal"].shift(1))
        for i in df.index[cross_dn]:
            signals.append({"code": code, "date": i, "direction": "BUY", "price": float(close.loc[i])})
        for i in df.index[cross_up]:
            signals.append({"code": code, "date": i, "direction": "SELL", "price": float(close.loc[i])})

    signals.sort(key=lambda s: s["date"])
    return signals


def _signals_to_trades(
    signals: list[dict],
    include_cost: bool,
) -> list[dict]:
    """將訊號轉為完整交易紀錄（每次進出場配對）。"""
    trades: list[dict] = []
    open_positions: dict[str, dict] = {}  # code -> entry info

    for sig in signals:
        code = sig["code"]
        if sig["direction"] == "BUY" and code not in open_positions:
            open_positions[code] = {
                "entry_date": sig["date"],
                "entry_price": sig["price"],
            }
        elif sig["direction"] == "SELL" and code in open_positions:
            entry = open_positions.pop(code)
            ep = entry["entry_price"]
            xp = sig["price"]
            shares = 1000

            cost = (ep + xp) * _DEFAULT_COST_RATE / 2 * shares if include_cost else 0.0
            pnl = (xp - ep) * shares - cost
            pnl_pct = (xp - ep) / ep * 100 if ep else 0.0

            entry_date = entry["entry_date"]
            exit_date = sig["date"]
            if hasattr(exit_date, "date"):
                exit_date = exit_date.date()
            if hasattr(entry_date, "date"):
                entry_date = entry_date.date()

            hold_days = (exit_date - entry_date).days if isinstance(exit_date, datetime.date) else 0

            trades.append({
                "代碼": code,
                "進場日": str(entry_date),
                "出場日": str(exit_date),
                "進場價": round(ep, 2),
                "出場價": round(xp, 2),
                "損益": round(pnl, 0),
                "損益%": round(pnl_pct, 2),
                "持有天數": hold_days,
            })

    return trades


def _calculate_metrics(trades: list[dict], initial_capital: float, start_date: Any, end_date: Any) -> dict:
    """從交易列表計算績效指標，對應 BacktestEngine._calculate_metrics 邏輯。"""
    if not trades:
        return {}

    pnls = [t["損益"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total_pnl = sum(pnls)
    final_capital = initial_capital + total_pnl
    total_return = total_pnl / initial_capital * 100

    # 年化報酬
    if isinstance(start_date, datetime.date) and isinstance(end_date, datetime.date):
        days = (end_date - start_date).days or 1
    else:
        days = 252
    annual_return = total_return * (365 / days)

    # Sharpe
    daily_returns = np.array(pnls) / initial_capital
    sharpe = 0.0
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        sharpe = float(np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252))

    # 最大回撤
    equity_arr = np.cumsum([initial_capital] + pnls)
    peak = np.maximum.accumulate(equity_arr)
    drawdown = (peak - equity_arr) / peak
    max_dd = float(np.max(drawdown)) * 100 if len(drawdown) > 0 else 0.0

    # 勝率、獲利因子
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 1.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    return {
        "total_return": round(total_return, 2),
        "annual_return": round(annual_return, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(max_dd, 2),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "final_capital": round(final_capital, 2),
        "total_trades": len(trades),
        "equity_curve": list(equity_arr),
    }


def _run_backtest(
    strategy: str,
    capital: float,
    include_cost: bool,
    max_stocks: int = 10,
) -> dict:
    """抓取股票資料、計算指標、生成訊號、計算績效。"""
    ind = get_indicator_lib()
    all_signals: list[dict] = []

    codes = [c for c, _ in TW_TOP_STOCKS[:max_stocks]]
    progress = st.progress(0, text="抓取股票資料中...")

    for idx, code in enumerate(codes):
        progress.progress((idx + 1) / len(codes), text=f"處理 {code} ({idx+1}/{len(codes)})")
        df = fetch_stock_data(code, period="1y")
        if df.empty:
            continue
        df = ind.calculate_all(df)
        sigs = _generate_signals(code, df, strategy)
        all_signals.extend(sigs)

    progress.empty()

    trades = _signals_to_trades(all_signals, include_cost)

    if not trades:
        return {"error": "回測期間無任何交易訊號，請更換策略或延長期間。"}

    # 推算日期範圍
    dates = [t["進場日"] for t in trades] + [t["出場日"] for t in trades]
    try:
        start_date = datetime.date.fromisoformat(min(dates))
        end_date = datetime.date.fromisoformat(max(dates))
    except Exception:
        start_date = end_date = datetime.date.today()

    metrics = _calculate_metrics(trades, capital, start_date, end_date)
    metrics["trades"] = trades
    return metrics


# ── 頁面 ─────────────────────────────────────────────────────────────────────

def render() -> None:
    st.title("回測分析")
    get_colors()

    # ── 控制面板 ────────────────────────────────
    with st.expander("回測設定", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            strategy = st.selectbox("策略", list(_STRATEGIES.keys()))
            st.caption(_STRATEGIES[strategy])
        with col2:
            max_stocks = st.slider("股票池大小（TW Top N）", 5, 30, 10)
        with col3:
            capital = st.number_input("初始資金", value=1_000_000, step=100_000, format="%d")

        col4, col5, col6 = st.columns(3)
        with col4:
            include_cost = st.checkbox("含交易成本", value=True)
        with col5:
            market = st.session_state.get("market", "TW")
            st.text(f"市場：{market}")
        with col6:
            run_clicked = st.button("執行回測", type="primary", use_container_width=True)

    if run_clicked:
        with st.spinner("執行回測中..."):
            result = _run_backtest(strategy, float(capital), include_cost, max_stocks)
        st.session_state["bt_result"] = result
        if "error" in result:
            st.warning(result["error"])
        else:
            st.success(f"回測完成，共 {result['total_trades']} 筆交易。")

    bt_result: dict | None = st.session_state.get("bt_result", None)

    # ── 回測結果摘要 ────────────────────────────
    st.divider()
    st.subheader("回測結果")

    if bt_result is None:
        st.info("請按「執行回測」開始分析。")
        _render_param_scan()
        return

    if "error" in bt_result:
        st.warning(bt_result["error"])
        _render_param_scan()
        return

    metrics = bt_result

    def _sign(v: float) -> str:
        return "positive" if v >= 0 else "negative"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(metric_card("總報酬", f"{metrics['total_return']:+.2f}%",
                                status=_sign(metrics["total_return"])), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("年化報酬", f"{metrics['annual_return']:+.2f}%",
                                status=_sign(metrics["annual_return"])), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("Sharpe", f"{metrics['sharpe']:.2f}",
                                status=_sign(metrics["sharpe"])), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("最大回撤", f"-{metrics['max_drawdown']:.2f}%",
                                status="negative"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card("勝率", f"{metrics['win_rate']:.1f}%",
                                status=_sign(metrics["win_rate"] - 50)), unsafe_allow_html=True)
    with c6:
        st.markdown(metric_card("獲利因子", f"{metrics['profit_factor']:.2f}",
                                status=_sign(metrics["profit_factor"] - 1)), unsafe_allow_html=True)

    # ── 淨值曲線 ────────────────────────────────
    st.divider()
    eq_curve = metrics.get("equity_curve", [])
    if eq_curve:
        fig = equity_curve(eq_curve, title="淨值曲線 + 回撤", height=500)
        st.plotly_chart(fig, use_container_width=True)

    # ── 交易明細 + R 倍數 + 蒙地卡羅 ──────────
    st.divider()
    tab1, tab2, tab3 = st.tabs(["交易明細", "R 倍數分佈", "蒙地卡羅"])

    trades: list[dict] = metrics.get("trades", [])

    with tab1:
        if trades:
            trades_df = pd.DataFrame(trades)
            st.dataframe(
                trades_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "損益%": st.column_config.NumberColumn(format="%.2f%%"),
                    "損益": st.column_config.NumberColumn(format="%,.0f"),
                },
            )
        else:
            st.info("無交易紀錄。")

    with tab2:
        if trades:
            pnls = [t["損益"] for t in trades]
            avg_loss_amt = abs(np.mean([p for p in pnls if p <= 0])) if any(p <= 0 for p in pnls) else 1.0
            r_values = [p / avg_loss_amt for p in pnls]

            fig = histogram(r_values, title="R 倍數分佈", x_label="R 倍數", bins=25, height=400)
            st.plotly_chart(fig, use_container_width=True)

            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                st.metric("平均 R", f"{np.mean(r_values):.2f}")
            with col_r2:
                st.metric("中位數 R", f"{np.median(r_values):.2f}")
            with col_r3:
                win_rate_frac = metrics["win_rate"] / 100
                st.metric("期望值 (EV)", f"{np.mean(r_values) * win_rate_frac:.2f}")
        else:
            st.info("無交易紀錄。")

    with tab3:
        _render_monte_carlo(trades, float(capital))

    # ── 參數掃描 ────────────────────────────────
    _render_param_scan()


def _render_monte_carlo(trades: list[dict], capital: float) -> None:
    st.subheader("蒙地卡羅模擬")
    mc_col1, mc_col2 = st.columns([1, 2])

    with mc_col1:
        mc_paths = st.slider("模擬路徑數", 100, 5000, 1000, 100, key="mc_paths")
        mc_run = st.button("執行模擬", use_container_width=True, key="mc_run")

    if mc_run:
        if not trades:
            st.warning("請先執行回測取得交易紀錄再進行蒙地卡羅模擬。")
            return

        pnl_list = [t["損益"] for t in trades]
        with st.spinner("蒙地卡羅模擬中..."):
            mc_result = get_monte_carlo().simulate(
                trades=pnl_list,
                num_paths=mc_paths,
                initial_capital=capital,
            )
        st.session_state["mc_result"] = mc_result

    mc_result = st.session_state.get("mc_result", None)

    with mc_col2:
        if mc_result is not None:
            # 用 percentile 值重建一個近似分佈用於直方圖展示
            finals_approx = np.interp(
                np.linspace(0, 100, 1000),
                [5, 25, 50, 75, 95],
                [mc_result.percentile_5, mc_result.percentile_25,
                 mc_result.percentile_50, mc_result.percentile_75,
                 mc_result.percentile_95],
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


def _render_param_scan() -> None:
    st.divider()
    st.subheader("參數網格掃描")
    with st.expander("設定參數範圍"):
        ps_col1, ps_col2 = st.columns(2)
        with ps_col1:
            st.text_input("MA 快線", value="5, 8, 13")
        with ps_col2:
            st.text_input("MA 慢線", value="21, 34, 55")
        st.button("開始掃描", use_container_width=True)
        st.caption("參數掃描功能開發中。")
