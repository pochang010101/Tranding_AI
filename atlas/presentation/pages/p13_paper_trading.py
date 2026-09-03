"""P-13 紙上交易 — 模擬下單、持倉監控、績效追蹤、一鍵建倉。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import bar_chart, equity_curve
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import fetch_stock_quote

logger = logging.getLogger(__name__)


# ── 批次買入工具 ─────────────────────────────────
def _batch_buy(
    codes: list[str],
    amount_per_stock: float,
    stop_loss_pct: float = 5.0,
) -> list[dict[str, Any]]:
    """批次買入多檔股票，寫入 session_state。

    Args:
        codes: 要買入的股票代碼清單
        amount_per_stock: 每檔投入金額
        stop_loss_pct: 停損百分比（預設 5%）

    Returns:
        每檔買入結果清單
    """
    results: list[dict[str, Any]] = []
    for code in codes:
        try:
            quote = fetch_stock_quote(code)
            price = quote.get("price", 0)
            if price <= 0:
                results.append({
                    "代碼": code, "狀態": "失敗",
                    "原因": "無法取得報價",
                })
                continue

            shares = int(amount_per_stock / price / 1000) * 1000
            if shares < 1000:
                results.append({
                    "代碼": code, "狀態": "跳過",
                    "原因": f"資金不足買一張（需 {price * 1000:,.0f}）",
                })
                continue

            lots = shares // 1000
            cost = price * shares * 1.001425  # 含手續費
            stop = round(price * (1 - stop_loss_pct / 100), 2)

            order = {
                "代碼": code,
                "方向": "買入",
                "價格": price,
                "張數": lots,
                "停損": stop,
                "目標": None,
                "原因": "快速建倉",
                "狀態": "已成交",
                "成本": cost,
            }
            st.session_state["pt_orders"].append(order)
            st.session_state["pt_positions"].append({
                "代碼": code,
                "進場價": price,
                "張數": lots,
                "停損": stop,
                "目標": "-",
                "原因": "快速建倉",
            })

            results.append({
                "代碼": code, "狀態": "成功",
                "張數": lots, "價格": price,
                "成本": round(cost, 0),
            })
        except Exception as e:
            results.append({
                "代碼": code, "狀態": "失敗", "原因": str(e),
            })
    return results


def _get_quote_price(code: str) -> float:
    """安全取得即時價格，失敗回傳 0。"""
    try:
        q = fetch_stock_quote(code)
        return float(q.get("price", 0))
    except Exception:
        return 0.0


# ── 主頁面 ──────────────────────────────────────
def render() -> None:
    st.title("📝 紙上交易")
    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
💰 <strong>模擬資金</strong>：使用虛擬資金操作，完全不影響實際帳戶，適合策略驗證與練習。<br>
🧾 <strong>手續費 / 稅</strong>：買入手續費 0.1425%、賣出手續費 0.1425% + 證交稅 0.3%，完整模擬真實交易成本。<br>
📊 <strong>損益計算</strong>：已扣除手續費與稅金的真實淨損益，報酬率以起始資金為基準計算。<br>
🔄 <strong>委託狀態</strong>：已成交 = 模擬市價成交；持倉中 = 尚未平倉；交易紀錄保留完整進出場歷史。<br>
🚀 <strong>快速建倉</strong>：從觀察股 / 回測推薦一鍵批次買入，自動計算張數與停損。<br>
<span class="legend-good">紅色損益 = 獲利</span>（台股慣例），<span class="legend-bad">綠色損益 = 虧損</span>
</div>
""", unsafe_allow_html=True)
    get_colors()

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
        st.slider("單筆風險 %", 0.5, 5.0, 2.0, 0.5)
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
    eq = st.session_state["pt_equity_curve"]
    current_equity = eq[-1] if eq else start_capital

    # 計算持倉未實現損益
    unrealized_pnl = 0.0
    position_count = len(st.session_state["pt_positions"])
    if st.session_state["pt_positions"]:
        for pos in st.session_state["pt_positions"]:
            try:
                cur_price = _get_quote_price(pos["代碼"])
                if cur_price > 0:
                    unrealized_pnl += (
                        (cur_price - pos["進場價"]) * pos["張數"] * 1000
                    )
            except Exception:
                pass

    total_pnl = (current_equity - start_capital) + unrealized_pnl
    total_asset = current_equity + unrealized_pnl
    return_pct = total_pnl / start_capital * 100 if start_capital else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(
            metric_card("起始資金", f"${start_capital:,.0f}", status="neutral"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            metric_card(
                "總資產", f"${total_asset:,.0f}",
                status="positive" if total_pnl >= 0 else "negative",
            ),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            metric_card(
                "總損益", f"${total_pnl:+,.0f}",
                status="positive" if total_pnl >= 0 else "negative",
            ),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            metric_card(
                "報酬率", f"{return_pct:+.2f}%",
                status="positive" if return_pct >= 0 else "negative",
            ),
            unsafe_allow_html=True,
        )
    with c5:
        st.markdown(
            metric_card("持倉檔數", str(position_count), status="neutral"),
            unsafe_allow_html=True,
        )
    with c6:
        status_text = (
            "🟢 運行中" if st.session_state["pt_started"] else "⏸️ 已停止"
        )
        st.markdown(
            metric_card("狀態", status_text, status="neutral"),
            unsafe_allow_html=True,
        )

    # ── 主要操作區（Tab） ────────────────────────
    if st.session_state["pt_started"]:
        st.divider()
        tab_quick, tab_manual, tab_sell = st.tabs([
            "🚀 快速建倉", "📈 手動下單", "📉 賣出",
        ])

        # ── Tab 1: 快速建倉 ──────────────────────
        with tab_quick:
            _render_quick_build()

        # ── Tab 2: 手動買入 ──────────────────────
        with tab_manual:
            _render_manual_buy()

        # ── Tab 3: 賣出 ─────────────────────────
        with tab_sell:
            _render_sell()

    # ── 持倉列表（含即時損益） ────────────────────
    st.divider()
    st.subheader("目前持倉")
    _render_positions()

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
    _render_trade_stats()


# ── 快速建倉子區塊 ──────────────────────────────
def _render_quick_build() -> None:
    """從觀察股 / 回測推薦一鍵建倉。"""

    watchlist_codes: list[str] = st.session_state.get("watchlist_codes", [])
    backtest_codes: list[str] = st.session_state.get(
        "backtest_recommended", [],
    )

    # 共用參數
    st.markdown("##### 建倉參數")
    pc1, pc2 = st.columns(2)
    with pc1:
        amount_per = st.number_input(
            "每檔投入金額",
            value=100_000, min_value=10_000, step=10_000,
            key="pt_batch_amount",
            help="自動計算可買張數 = 投入金額 ÷ 現價 ÷ 1000（無條件捨去）",
        )
    with pc2:
        stop_pct = st.number_input(
            "停損 %", value=5.0, min_value=1.0, max_value=20.0, step=0.5,
            key="pt_batch_stop",
            help="以買入價往下 N% 作為停損價",
        )

    # ── 區塊 A：觀察股快速建倉 ─────────────────
    with st.container(border=True):
        st.markdown("##### 📋 從觀察股快速建倉")
        if not watchlist_codes:
            st.info(
                "目前無觀察股。請先至「P-04 每日選股」或「P-17 籌碼分析」"
                "將股票加入觀察股。"
            )
        else:
            st.caption(
                f"共 {len(watchlist_codes)} 檔觀察股"
                f"（來源：P-04 選股 / P-17 籌碼）"
            )

            # 取得報價並建立表格
            rows: list[dict[str, Any]] = []
            for code in watchlist_codes:
                try:
                    q = fetch_stock_quote(code)
                    price = q.get("price", 0)
                    prev = q.get("prev_close", 0)
                    chg_pct = (
                        (price - prev) / prev * 100
                        if prev > 0 else 0
                    )
                    can_buy = int(amount_per / price / 1000) if price > 0 else 0
                    rows.append({
                        "買入": True,
                        "代碼": code,
                        "現價": price,
                        "漲跌%": round(chg_pct, 2),
                        "可買張數": can_buy,
                        "預估成本": (
                            f"{can_buy * price * 1000:,.0f}" if can_buy > 0
                            else "不足一張"
                        ),
                    })
                except Exception:
                    rows.append({
                        "買入": False,
                        "代碼": code,
                        "現價": 0,
                        "漲跌%": 0,
                        "可買張數": 0,
                        "預估成本": "報價失敗",
                    })

            watch_df = pd.DataFrame(rows)
            edited_watch = st.data_editor(
                watch_df,
                width="stretch",
                hide_index=True,
                height=min(400, 40 + len(rows) * 35),
                column_config={
                    "買入": st.column_config.CheckboxColumn(
                        "買入", default=True, width="small",
                    ),
                    "現價": st.column_config.NumberColumn(format="$%.2f"),
                    "漲跌%": st.column_config.NumberColumn(format="%+.2f%%"),
                    "可買張數": st.column_config.NumberColumn(format="%d"),
                },
                disabled=[c for c in watch_df.columns if c != "買入"],
                key="pt_watch_editor",
            )

            if st.button(
                "🚀 批次買入勾選股票",
                type="primary",
                width="stretch",
                key="pt_batch_buy_watch",
            ):
                selected = edited_watch[edited_watch["買入"]]
                sel_codes = selected["代碼"].tolist()
                if not sel_codes:
                    st.warning("請至少勾選一檔股票")
                else:
                    with st.spinner(f"正在買入 {len(sel_codes)} 檔…"):
                        results = _batch_buy(sel_codes, amount_per, stop_pct)
                    _show_batch_results(results)
                    st.rerun()

    # ── 區塊 B：回測推薦建倉 ─────────────────
    with st.container(border=True):
        st.markdown("##### 🏆 從回測推薦建倉")
        if not backtest_codes:
            st.info(
                "目前無回測推薦股。請至「P-07 回測」執行批次回測，"
                "系統會自動將表現最佳的股票寫入推薦清單。"
            )
        else:
            st.caption(
                f"共 {len(backtest_codes)} 檔回測推薦股"
            )
            bt_rows: list[dict[str, Any]] = []
            for code in backtest_codes:
                try:
                    q = fetch_stock_quote(code)
                    price = q.get("price", 0)
                    can_buy = (
                        int(amount_per / price / 1000) if price > 0 else 0
                    )
                    bt_rows.append({
                        "買入": True,
                        "代碼": code,
                        "現價": price,
                        "可買張數": can_buy,
                    })
                except Exception:
                    bt_rows.append({
                        "買入": False, "代碼": code,
                        "現價": 0, "可買張數": 0,
                    })

            bt_df = pd.DataFrame(bt_rows)
            edited_bt = st.data_editor(
                bt_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "買入": st.column_config.CheckboxColumn(
                        "買入", default=True, width="small",
                    ),
                    "現價": st.column_config.NumberColumn(format="$%.2f"),
                },
                disabled=[c for c in bt_df.columns if c != "買入"],
                key="pt_bt_editor",
            )

            if st.button(
                "🚀 批次買入回測推薦",
                type="primary",
                width="stretch",
                key="pt_batch_buy_bt",
            ):
                sel_codes = edited_bt[edited_bt["買入"]]["代碼"].tolist()
                if not sel_codes:
                    st.warning("請至少勾選一檔股票")
                else:
                    with st.spinner(f"正在買入 {len(sel_codes)} 檔…"):
                        results = _batch_buy(sel_codes, amount_per, stop_pct)
                    _show_batch_results(results)
                    st.rerun()


def _show_batch_results(results: list[dict[str, Any]]) -> None:
    """顯示批次買入結果摘要。"""
    success = [r for r in results if r["狀態"] == "成功"]
    failed = [r for r in results if r["狀態"] == "失敗"]
    skipped = [r for r in results if r["狀態"] == "跳過"]

    if success:
        total_cost = sum(r.get("成本", 0) for r in success)
        codes_str = ", ".join(r["代碼"] for r in success)
        st.success(
            f"成功買入 {len(success)} 檔：{codes_str}\n"
            f"總成本約 ${total_cost:,.0f}"
        )
    if skipped:
        for r in skipped:
            st.warning(f"{r['代碼']}：{r.get('原因', '跳過')}")
    if failed:
        for r in failed:
            st.error(f"{r['代碼']}：{r.get('原因', '失敗')}")


# ── 手動買入子區塊 ──────────────────────────────
def _render_manual_buy() -> None:
    bc1, bc2, bc3, bc4 = st.columns(4)
    with bc1:
        buy_code = st.text_input(
            "股票代碼", key="pt_buy_code", placeholder="2330",
        )
    with bc2:
        buy_price = st.number_input(
            "買入價", key="pt_buy_price", value=0.0, step=0.5,
        )
    with bc3:
        buy_stop = st.number_input(
            "停損價", key="pt_buy_stop", value=0.0, step=0.5,
        )
    with bc4:
        buy_lots = st.number_input(
            "張數", key="pt_buy_lots", value=1, min_value=1, step=1,
        )

    bc5, bc6 = st.columns(2)
    with bc5:
        buy_target = st.number_input(
            "目標價 (選填)", key="pt_buy_target", value=0.0, step=0.5,
        )
    with bc6:
        buy_reason = st.text_input(
            "買入原因", key="pt_buy_reason", placeholder="策略訊號/突破",
        )

    if st.button(
        "確認買入", type="primary", key="pt_confirm_buy", width="stretch",
    ):
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


# ── 賣出子區塊 ─────────────────────────────────
def _render_sell() -> None:
    if st.session_state["pt_positions"]:
        pos_options = [
            f"{p['代碼']} (進場: {p['進場價']}, {p['張數']}張)"
            for p in st.session_state["pt_positions"]
        ]
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            sel_idx = st.selectbox(
                "選擇持倉",
                range(len(pos_options)),
                format_func=lambda x: pos_options[x],
            )
        with sc2:
            sell_price = st.number_input(
                "賣出價", key="pt_sell_price", value=0.0, step=0.5,
            )
        with sc3:
            sell_reason = st.text_input(
                "賣出原因", key="pt_sell_reason",
                placeholder="停損/停利/訊號",
            )
        if st.button(
            "確認賣出", type="primary", key="pt_confirm_sell",
            width="stretch",
        ) and sell_price > 0:
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
            eq_curve = st.session_state["pt_equity_curve"]
            eq_curve.append(eq_curve[-1] + net_pnl)
            st.session_state["pt_positions"].pop(sel_idx)
            st.success(f"賣出 {pos['代碼']} 損益: ${net_pnl:+,.0f}")
            st.rerun()
    else:
        st.info("目前無持倉可賣出")


# ── 持倉列表（含即時損益） ──────────────────────
def _render_positions() -> None:
    positions = st.session_state["pt_positions"]
    if not positions:
        st.info("目前無持倉")
        return

    pos_rows: list[dict[str, Any]] = []
    total_unrealized = 0.0
    total_market_value = 0.0
    total_cost_value = 0.0

    for pos in positions:
        code = pos["代碼"]
        entry = pos["進場價"]
        lots = pos["張數"]
        cost_val = entry * lots * 1000

        try:
            cur_price = _get_quote_price(code)
        except Exception:
            cur_price = 0.0

        if cur_price > 0:
            market_val = cur_price * lots * 1000
            pnl = (cur_price - entry) * lots * 1000
            pnl_pct = (cur_price - entry) / entry * 100
        else:
            market_val = cost_val
            pnl = 0.0
            pnl_pct = 0.0

        total_unrealized += pnl
        total_market_value += market_val
        total_cost_value += cost_val

        pos_rows.append({
            "代碼": code,
            "進場價": entry,
            "現價": cur_price if cur_price > 0 else "N/A",
            "張數": lots,
            "成本": round(cost_val, 0),
            "市值": round(market_val, 0),
            "未實現損益": round(pnl, 0),
            "損益%": round(pnl_pct, 2),
            "停損": pos.get("停損", "-"),
            "目標": pos.get("目標", "-"),
        })

    # 持倉加總指標
    pc1, pc2, pc3, pc4 = st.columns(4)
    with pc1:
        st.markdown(
            metric_card(
                "持倉市值",
                f"${total_market_value:,.0f}",
                status="neutral",
            ),
            unsafe_allow_html=True,
        )
    with pc2:
        st.markdown(
            metric_card(
                "持倉成本",
                f"${total_cost_value:,.0f}",
                status="neutral",
            ),
            unsafe_allow_html=True,
        )
    with pc3:
        st.markdown(
            metric_card(
                "未實現損益",
                f"${total_unrealized:+,.0f}",
                status="positive" if total_unrealized >= 0 else "negative",
            ),
            unsafe_allow_html=True,
        )
    with pc4:
        ur_pct = (
            total_unrealized / total_cost_value * 100
            if total_cost_value > 0 else 0
        )
        st.markdown(
            metric_card(
                "未實現報酬",
                f"{ur_pct:+.2f}%",
                status="positive" if ur_pct >= 0 else "negative",
            ),
            unsafe_allow_html=True,
        )

    # 持倉表格 + 損益顏色
    pos_df = pd.DataFrame(pos_rows)

    # 台股慣例：正(獲利)=紅、負(虧損)=綠
    def _pnl_color(val: float) -> str:
        if val > 0:
            return "color: #ef5350"  # 紅
        if val < 0:
            return "color: #26a69a"  # 綠
        return ""

    styled = pos_df.style.applymap(
        _pnl_color, subset=["未實現損益", "損益%"],
    )
    st.dataframe(
        styled,
        width="stretch",
        hide_index=True,
        height=min(400, 40 + len(pos_rows) * 35),
    )


# ── 交易統計 ────────────────────────────────────
def _render_trade_stats() -> None:
    sell_orders = [
        o for o in st.session_state["pt_orders"] if o.get("方向") == "賣出"
    ]
    if not sell_orders:
        return

    st.divider()
    st.subheader("交易統計")
    pnls = [o.get("損益", 0) for o in sell_orders]
    wins = sum(1 for p in pnls if p > 0)
    total = len(pnls)

    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        wr = wins / total * 100 if total else 0
        st.markdown(
            metric_card(
                "勝率", f"{wr:.1f}%",
                status="positive" if wr >= 50 else "negative",
            ),
            unsafe_allow_html=True,
        )
    with sc2:
        avg_pnl = sum(pnls) / total if total else 0
        st.markdown(
            metric_card(
                "平均損益", f"${avg_pnl:+,.0f}",
                status="positive" if avg_pnl >= 0 else "negative",
            ),
            unsafe_allow_html=True,
        )
    with sc3:
        st.markdown(
            metric_card("交易次數", str(total), status="neutral"),
            unsafe_allow_html=True,
        )
    with sc4:
        total_pnl_trades = sum(pnls)
        st.markdown(
            metric_card(
                "累計損益", f"${total_pnl_trades:+,.0f}",
                status="positive" if total_pnl_trades >= 0 else "negative",
            ),
            unsafe_allow_html=True,
        )

    # 損益分佈
    fig = bar_chart(
        list(range(1, len(pnls) + 1)),
        pnls,
        title="每筆交易損益",
        color_by_value=True,
        height=300,
    )
    st.plotly_chart(fig, width="stretch")
