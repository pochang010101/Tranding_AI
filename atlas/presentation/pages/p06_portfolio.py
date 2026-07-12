"""P-06 持倉追蹤 — 持倉列表、進出場紀錄、績效統計。"""

from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import equity_curve, histogram
from atlas.presentation.components.theme import get_colors, metric_card


def _run_async(coro):
    """在同步 Streamlit 環境中執行 async 函式。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except Exception:
        return None


def _fetch_current_price(code: str) -> float | None:
    """呼叫 fetch_stock_quote 取得即時現價，失敗回傳 None。"""
    try:
        from atlas.infrastructure.services.service_container import fetch_stock_quote
        result = _run_async(fetch_stock_quote(code))
        if result and hasattr(result, "price"):
            return float(result.price)
        if isinstance(result, dict):
            return float(result.get("price") or result.get("close") or 0) or None
    except Exception:
        pass
    return None


def _build_positions_df(positions: list[dict[str, Any]]) -> pd.DataFrame:
    """將 session_state 持倉清單轉成含未實現損益的 DataFrame。"""
    rows = []
    for pos in positions:
        code: str = str(pos.get("代碼", ""))
        name: str = str(pos.get("名稱", ""))
        entry_price: float = float(pos.get("進場價", 0))
        lots: int = int(pos.get("張數", 0))
        stop: float = float(pos.get("停損", 0))
        target: float = float(pos.get("停利", 0))

        current_price = _fetch_current_price(code) if code else None
        if current_price is None:
            current_price = entry_price  # fallback：未能取得報價時顯示進場價

        shares = lots * 1000
        unrealized_pnl = (current_price - entry_price) * shares
        pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price else 0.0
        risk_per_share = entry_price - stop if stop and entry_price > stop else 1
        r_value = (current_price - entry_price) / risk_per_share if risk_per_share else 0.0

        rows.append({
            "代碼": code,
            "名稱": name,
            "進場價": entry_price,
            "現價": current_price,
            "張數": lots,
            "停損": stop,
            "目標": target,
            "未實現損益": int(unrealized_pnl),
            "損益%": pnl_pct,
            "R倍數": round(r_value, 2),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["代碼", "名稱", "進場價", "現價", "張數", "停損", "目標", "未實現損益", "損益%", "R倍數"]
    )


def _calc_performance(
    orders: list[dict[str, Any]],
    capital: float,
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    """從已平倉訂單計算績效指標。"""
    sell_orders = [o for o in orders if o.get("方向") == "賣出"]

    total_pnl = sum(float(o.get("損益", 0)) for o in sell_orders)
    winning = [o for o in sell_orders if float(o.get("損益", 0)) > 0]
    win_rate = len(winning) / len(sell_orders) * 100 if sell_orders else 0.0

    # 估算 R：pnl / (entry_price * 0.03 * shares)，以 3% 為基準風險單位
    r_values: list[float] = []
    for o in sell_orders:
        pnl = float(o.get("損益", 0))
        price = float(o.get("價格", 0))
        lots = int(o.get("張數", 1))
        risk_unit = price * 0.03 * lots * 1000
        if risk_unit > 0:
            r_values.append(pnl / risk_unit)

    avg_r = sum(r_values) / len(r_values) if r_values else 0.0
    expected_value = total_pnl / len(sell_orders) if sell_orders else 0.0

    # 帳戶淨值 = 現金 + 未實現損益（用進場價估算，因 fetch_stock_quote 已在 positions_df 做了）
    unrealized_total = 0.0
    for pos in positions:
        entry = float(pos.get("進場價", 0))
        lots = int(pos.get("張數", 0))
        unrealized_total += entry * lots * 1000  # 持倉市值（保守用進場價）
    account_equity = capital + unrealized_total

    return {
        "account_equity": account_equity,
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "avg_r": avg_r,
        "expected_value": expected_value,
        "r_values": r_values,
        "sell_count": len(sell_orders),
    }


def render() -> None:
    st.title("💼 持倉追蹤")
    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
<b>持倉損益</b>：正值=獲利中（綠）、負值=虧損中（紅）｜
<b>R-multiple</b>：以初始風險(R)衡量報酬，&gt;2R=優秀、1~2R=良好、&lt;0=虧損｜
<b>部位大小</b>：佔總資金比例，單一部位建議&lt;10%，總曝險&lt;60%｜
<b>停損價</b>：跌破即出場的價位，紀律執行是風控核心
</div>
""", unsafe_allow_html=True)
    get_colors()

    # ── 讀取 session_state ───────────────────────
    positions: list[dict] = st.session_state.get("pt_positions", [])
    orders: list[dict] = st.session_state.get("pt_orders", [])
    capital: float = float(st.session_state.get("pt_capital", 1_000_000))
    equity_curve_data: list[float] = st.session_state.get("pt_equity_curve", [capital])

    perf = _calc_performance(orders, capital, positions)

    # ── 績效總覽 ────────────────────────────────
    st.subheader("績效總覽")
    c1, c2, c3, c4, c5 = st.columns(5)

    equity_val = perf["account_equity"]
    pnl_pct = (equity_val / 1_000_000 - 1) * 100 if equity_val else 0.0

    with c1:
        st.markdown(
            metric_card("帳戶淨值", f"${equity_val:,.0f}",
                        status="positive" if equity_val >= 1_000_000 else "negative"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            metric_card("總損益", f"{pnl_pct:+.2f}%",
                        status="positive" if pnl_pct >= 0 else "negative"),
            unsafe_allow_html=True,
        )
    with c3:
        wr = perf["win_rate"]
        st.markdown(
            metric_card("勝率", f"{wr:.1f}%" if perf["sell_count"] else "—",
                        status="positive" if wr >= 50 else "negative"),
            unsafe_allow_html=True,
        )
    with c4:
        avg_r = perf["avg_r"]
        st.markdown(
            metric_card("平均 R", f"{avg_r:+.2f}" if perf["sell_count"] else "—",
                        status="positive" if avg_r >= 1 else "negative"),
            unsafe_allow_html=True,
        )
    with c5:
        ev = perf["expected_value"]
        st.markdown(
            metric_card("期望值/筆", f"${ev:+,.0f}" if perf["sell_count"] else "—",
                        status="positive" if ev >= 0 else "negative"),
            unsafe_allow_html=True,
        )

    # ── 未平倉持倉 ──────────────────────────────
    st.divider()
    st.subheader("未平倉持倉")

    if positions:
        with st.spinner("更新即時報價…"):
            pos_df = _build_positions_df(positions)
        st.dataframe(
            pos_df,
            width="stretch",
            hide_index=True,
            column_config={
                "損益%": st.column_config.NumberColumn(format="%+.2f%%"),
                "未實現損益": st.column_config.NumberColumn(format="$%+,d"),
                "R倍數": st.column_config.NumberColumn(format="%+.2f"),
            },
        )
    else:
        st.info("目前沒有未平倉持倉。可至「模擬交易」頁面建倉，或透過下方「建倉」表單手動新增。")

    # ── 建倉 / 平倉 / 倉位計算 ──────────────────
    st.divider()
    tab_add, tab_close, tab_calc = st.tabs(["➕ 建倉", "❌ 平倉", "🔢 倉位計算"])

    with tab_add:
        ac1, ac2, ac3, ac4 = st.columns(4)
        with ac1:
            new_code = st.text_input("代碼", key="add_code", placeholder="2330")
        with ac2:
            new_price = st.number_input("進場價", key="add_price", value=0.0, step=0.5)
        with ac3:
            new_stop = st.number_input("停損價", key="add_stop", value=0.0, step=0.5)
        with ac4:
            new_lots = st.number_input("張數", key="add_lots", value=1, step=1)

        if st.button("確認建倉", type="primary", width="stretch"):
            if new_code and new_price > 0 and new_stop > 0 and new_lots > 0:
                pos_list: list[dict] = st.session_state.get("pt_positions", [])
                pos_list.append({
                    "代碼": new_code.strip(),
                    "名稱": new_code.strip(),
                    "進場價": new_price,
                    "張數": int(new_lots),
                    "停損": new_stop,
                    "停利": 0.0,
                })
                st.session_state["pt_positions"] = pos_list
                st.success(f"已建倉 {new_code} × {int(new_lots)} 張 @ {new_price}")
                st.rerun()
            else:
                st.warning("請填入代碼、進場價、停損價、張數。")

    with tab_close:
        if not positions:
            st.info("目前無持倉可平倉。")
        else:
            pos_labels = [f"{p.get('代碼','')} {p.get('名稱','')}" for p in positions]
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                selected_label = st.selectbox("選擇持倉", pos_labels, key="close_select")
            with cc2:
                close_price = st.number_input("出場價", key="close_price", value=0.0, step=0.5)
            with cc3:
                close_reason = st.text_input("出場原因", key="close_reason", placeholder="停損/停利/訊號")

            if st.button("確認平倉", type="primary", width="stretch"):
                if close_price > 0 and selected_label:
                    idx = pos_labels.index(selected_label)
                    pos = positions[idx]
                    entry = float(pos.get("進場價", 0))
                    lots = int(pos.get("張數", 1))
                    pnl = (close_price - entry) * lots * 1000

                    order_list: list[dict] = st.session_state.get("pt_orders", [])
                    import datetime
                    order_list.append({
                        "代碼": pos.get("代碼", ""),
                        "名稱": pos.get("名稱", ""),
                        "方向": "賣出",
                        "價格": close_price,
                        "張數": lots,
                        "時間": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "損益": round(pnl, 0),
                        "原因": close_reason,
                    })
                    st.session_state["pt_orders"] = order_list

                    new_pos = [p for i, p in enumerate(positions) if i != idx]
                    st.session_state["pt_positions"] = new_pos

                    # 更新 capital 與 equity_curve
                    new_capital = capital + pnl
                    st.session_state["pt_capital"] = new_capital
                    curve: list[float] = st.session_state.get("pt_equity_curve", [1_000_000])
                    curve.append(new_capital)
                    st.session_state["pt_equity_curve"] = curve

                    st.success(f"已平倉 {selected_label}，損益 ${pnl:+,.0f}")
                    st.rerun()
                else:
                    st.warning("請填入出場價。")

    with tab_calc:
        st.subheader("ATR 動態倉位計算")
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            entry = st.number_input("預計進場價", value=100.0, step=0.5, key="calc_entry")
        with pc2:
            stop_calc = st.number_input("停損價", value=95.0, step=0.5, key="calc_stop")
        with pc3:
            risk_pct = st.slider("風險百分比 %", 0.5, 5.0, 2.0, 0.5)

        if entry > 0 and stop_calc > 0 and entry != stop_calc:
            risk_amount = capital * risk_pct / 100
            risk_per_share = abs(entry - stop_calc)
            lots = max(1, int(risk_amount / risk_per_share / 1000))
            st.success(
                f"建議買入 **{lots} 張**（{lots * 1000} 股），"
                f"風險金額 ${lots * 1000 * risk_per_share:,.0f}（帳戶 {risk_pct}%）"
            )

    # ── 歷史績效曲線 ────────────────────────────
    st.divider()
    st.subheader("歷史績效曲線")

    if len(equity_curve_data) >= 2:
        fig = equity_curve(equity_curve_data, height=400)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("尚無足夠的淨值歷史紀錄（需至少完成一筆平倉交易後才會顯示曲線）。")

    # ── R 倍數分佈 ──────────────────────────────
    st.divider()
    st.subheader("R 倍數分佈")

    r_values = perf["r_values"]
    if r_values:
        fig = histogram(r_values, title="已平倉 R 倍數", x_label="R", bins=20, height=350)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("尚無已平倉紀錄，R 倍數分佈將在完成第一筆平倉後顯示。")

    # ── 已平倉訂單紀錄 ──────────────────────────
    if orders:
        st.divider()
        st.subheader("已平倉紀錄")
        orders_df = pd.DataFrame(orders)
        st.dataframe(orders_df, width="stretch", hide_index=True)
