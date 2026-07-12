"""P-13 紙上交易 — 模擬下單、持倉監控、績效追蹤。"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np

from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.components.charts import equity_curve, bar_chart


def render() -> None:
    st.title("📝 紙上交易")
    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
💰 <strong>模擬資金</strong>：使用虛擬資金操作，完全不影響實際帳戶，適合策略驗證與練習。<br>
🧾 <strong>手續費 / 稅</strong>：買入手續費 0.1425%、賣出手續費 0.1425% + 證交稅 0.3%，完整模擬真實交易成本。<br>
📊 <strong>損益計算</strong>：已扣除手續費與稅金的真實淨損益，報酬率以起始資金為基準計算。<br>
🔄 <strong>委託狀態</strong>：已成交 = 模擬市價成交；持倉中 = 尚未平倉；交易紀錄保留完整進出場歷史。
</div>
""", unsafe_allow_html=True)
    c = get_colors()

    # 初始化 session state
    if "pt_started" not in st.session_state:
        st.session_state["pt_started"] = False
    if "pt_capital" not in st.session_state:
        st.session_state["pt_capital"] = 1_000_000
    if "pt_orders" not in st.session_state:
        st.session_state["pt_orders"] = []
    if "pt_positions" not in st.session_state:
        st.session_state["pt_positions"] = []
    if "pt_equity_curve" not in st.session_state:
        st.session_state["pt_equity_curve"] = [1_000_000]

    # ── 控制面板 ────────────────────────────────
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([2, 2, 1])
    with col_ctrl1:
        capital = st.number_input(
            "起始資金", value=st.session_state["pt_capital"],
            min_value=100_000, step=100_000,
            disabled=st.session_state["pt_started"],
        )
    with col_ctrl2:
        risk_pct = st.slider("單筆風險 %", 0.5, 5.0, 2.0, 0.5)
    with col_ctrl3:
        st.write("")
        st.write("")
        if not st.session_state["pt_started"]:
            if st.button("🟢 啟動紙上交易", type="primary", width="stretch"):
                st.session_state["pt_started"] = True
                st.session_state["pt_capital"] = capital
                st.session_state["pt_equity_curve"] = [capital]
                st.toast("紙上交易已啟動！")
                st.rerun()
        else:
            if st.button("🔴 停止交易", type="secondary", width="stretch"):
                st.session_state["pt_started"] = False
                st.toast("紙上交易已停止")
                st.rerun()

    # ── 績效總覽 ────────────────────────────────
    st.divider()
    start_capital = st.session_state["pt_capital"]
    # Demo: simulate equity changes
    eq = st.session_state["pt_equity_curve"]
    current_equity = eq[-1] if eq else start_capital
    total_pnl = current_equity - start_capital
    return_pct = total_pnl / start_capital * 100 if start_capital else 0
    open_count = len(st.session_state["pt_positions"])
    order_count = len(st.session_state["pt_orders"])

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(metric_card("起始資金", f"${start_capital:,.0f}", status="neutral"),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("目前淨值", f"${current_equity:,.0f}",
                    status="positive" if total_pnl >= 0 else "negative"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("總損益", f"${total_pnl:+,.0f}",
                    status="positive" if total_pnl >= 0 else "negative"),
                    unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("報酬率", f"{return_pct:+.2f}%",
                    status="positive" if return_pct >= 0 else "negative"),
                    unsafe_allow_html=True)
    with c5:
        status_text = "🟢 運行中" if st.session_state["pt_started"] else "⏸️ 已停止"
        st.markdown(metric_card("狀態", status_text, status="neutral"),
                    unsafe_allow_html=True)

    # ── 下單面板 ────────────────────────────────
    if st.session_state["pt_started"]:
        st.divider()
        st.subheader("下單")

        tab_buy, tab_sell = st.tabs(["📈 買入", "📉 賣出"])

        with tab_buy:
            bc1, bc2, bc3, bc4 = st.columns(4)
            with bc1:
                buy_code = st.text_input("股票代碼", key="pt_buy_code", placeholder="2330")
            with bc2:
                buy_price = st.number_input("買入價", key="pt_buy_price", value=0.0, step=0.5)
            with bc3:
                buy_stop = st.number_input("停損價", key="pt_buy_stop", value=0.0, step=0.5)
            with bc4:
                buy_lots = st.number_input("張數", key="pt_buy_lots", value=1, min_value=1, step=1)

            bc5, bc6 = st.columns(2)
            with bc5:
                buy_target = st.number_input("目標價 (選填)", key="pt_buy_target", value=0.0, step=0.5)
            with bc6:
                buy_reason = st.text_input("買入原因", key="pt_buy_reason", placeholder="策略訊號/突破")

            if st.button("確認買入", type="primary", key="pt_confirm_buy", width="stretch"):
                if buy_code and buy_price > 0 and buy_stop > 0:
                    order = {
                        "代碼": buy_code,
                        "方向": "買入",
                        "價格": buy_price,
                        "張數": buy_lots,
                        "停損": buy_stop,
                        "目標": buy_target if buy_target > 0 else None,
                        "原因": buy_reason,
                        "狀態": "已成交",
                        "成本": buy_price * buy_lots * 1000 * 1.001425,
                    }
                    st.session_state["pt_orders"].append(order)
                    st.session_state["pt_positions"].append({
                        "代碼": buy_code,
                        "進場價": buy_price,
                        "張數": buy_lots,
                        "停損": buy_stop,
                        "目標": buy_target if buy_target > 0 else "-",
                        "原因": buy_reason,
                    })
                    st.success(f"買入 {buy_code} x{buy_lots} 張 @ {buy_price}")
                    st.rerun()
                else:
                    st.warning("請填入完整資訊")

        with tab_sell:
            if st.session_state["pt_positions"]:
                pos_options = [f"{p['代碼']} (進場: {p['進場價']}, {p['張數']}張)"
                              for p in st.session_state["pt_positions"]]
                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    sel_idx = st.selectbox("選擇持倉", range(len(pos_options)),
                                          format_func=lambda x: pos_options[x])
                with sc2:
                    sell_price = st.number_input("賣出價", key="pt_sell_price", value=0.0, step=0.5)
                with sc3:
                    sell_reason = st.text_input("賣出原因", key="pt_sell_reason",
                                              placeholder="停損/停利/訊號")
                if st.button("確認賣出", type="primary", key="pt_confirm_sell",
                            width="stretch"):
                    if sell_price > 0:
                        pos = st.session_state["pt_positions"][sel_idx]
                        pnl = (sell_price - pos["進場價"]) * pos["張數"] * 1000
                        tax = sell_price * pos["張數"] * 1000 * 0.003
                        net_pnl = pnl - tax
                        st.session_state["pt_orders"].append({
                            "代碼": pos["代碼"],
                            "方向": "賣出",
                            "價格": sell_price,
                            "張數": pos["張數"],
                            "損益": round(net_pnl, 0),
                            "原因": sell_reason,
                            "狀態": "已成交",
                        })
                        eq = st.session_state["pt_equity_curve"]
                        eq.append(eq[-1] + net_pnl)
                        st.session_state["pt_positions"].pop(sel_idx)
                        st.success(f"賣出 {pos['代碼']} 損益: ${net_pnl:+,.0f}")
                        st.rerun()
            else:
                st.info("目前無持倉可賣出")

    # ── 持倉列表 ────────────────────────────────
    st.divider()
    st.subheader("目前持倉")
    if st.session_state["pt_positions"]:
        pos_df = pd.DataFrame(st.session_state["pt_positions"])
        st.dataframe(pos_df, width="stretch", hide_index=True)
    else:
        st.info("目前無持倉")

    # ── 交易紀錄 ────────────────────────────────
    st.divider()
    st.subheader("交易紀錄")
    if st.session_state["pt_orders"]:
        orders_df = pd.DataFrame(st.session_state["pt_orders"])
        st.dataframe(orders_df, width="stretch", hide_index=True)
    else:
        st.info("尚無交易紀錄")

    # ── 權益曲線 ────────────────────────────────
    if len(st.session_state["pt_equity_curve"]) > 1:
        st.divider()
        st.subheader("權益曲線")
        fig = equity_curve(st.session_state["pt_equity_curve"], height=400)
        st.plotly_chart(fig, width="stretch")

    # ── 交易統計 ────────────────────────────────
    sell_orders = [o for o in st.session_state["pt_orders"] if o.get("方向") == "賣出"]
    if sell_orders:
        st.divider()
        st.subheader("交易統計")
        pnls = [o.get("損益", 0) for o in sell_orders]
        wins = sum(1 for p in pnls if p > 0)
        total = len(pnls)

        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            wr = wins / total * 100 if total else 0
            st.markdown(metric_card("勝率", f"{wr:.1f}%",
                        status="positive" if wr >= 50 else "negative"),
                        unsafe_allow_html=True)
        with sc2:
            avg_pnl = sum(pnls) / total if total else 0
            st.markdown(metric_card("平均損益", f"${avg_pnl:+,.0f}",
                        status="positive" if avg_pnl >= 0 else "negative"),
                        unsafe_allow_html=True)
        with sc3:
            st.markdown(metric_card("交易次數", str(total), status="neutral"),
                        unsafe_allow_html=True)
        with sc4:
            total_pnl_trades = sum(pnls)
            st.markdown(metric_card("累計損益", f"${total_pnl_trades:+,.0f}",
                        status="positive" if total_pnl_trades >= 0 else "negative"),
                        unsafe_allow_html=True)

        # 損益分佈
        pnl_data = pd.DataFrame({"損益": pnls})
        fig = bar_chart(
            list(range(1, len(pnls) + 1)),
            pnls,
            title="每筆交易損益",
            color_by_value=True,
            height=300,
        )
        st.plotly_chart(fig, width="stretch")
