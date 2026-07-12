"""P-08 IPO 申購 — 申購列表、建議等級、蜜月期追蹤、歷史勝率。"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from atlas.presentation.components.charts import bar_chart
from atlas.presentation.components.theme import get_colors, metric_card
from atlas.presentation.service_container import (
    fetch_stock_quote,
    fetch_stock_data,
    get_indicator_lib,
)


def render() -> None:
    st.title("🆕 IPO 申購")
    c = get_colors()

    # ── 即將申購（自動抓取）──────────────────────
    st.subheader("最近新上市/上櫃")

    st.markdown("""
    <div class="legend-box">
    <strong>欄位說明</strong><br>
    <strong>申購區</strong>：只顯示尚未截止的公開申購（申購迄日 ≥ 今天），已截止自動隱藏<br>
    <span class="legend-good">價差%</span>：(市價 - 承銷價) / 承銷價，<span class="legend-good">&gt;20% 值得申購</span>、<span class="legend-warn">0~20% 小利</span>、<span class="legend-bad">&lt;0% 破發虧損</span><br>
    <strong>蜜月期</strong>：上市後 30 天內通常有股價蜜月效應，<span class="legend-good">報酬% &gt;0 賺</span>、<span class="legend-bad">&lt;0 賠</span><br>
    狀態：🟢 追蹤中（30天內）、🔴 蜜月結束（超過30天）
    </div>
    """, unsafe_allow_html=True)

    @st.cache_data(ttl=600, show_spinner="正在抓取最近 IPO 資料…")
    def _fetch_recent_ipos() -> list[dict]:
        """從 TWSE / TPEx 抓取最近新上市櫃資料。"""
        from atlas.strategy.ipo_module import IPOModule
        return IPOModule._fetch_upcoming_sync()

    fetched_ipos = _fetch_recent_ipos()
    if fetched_ipos:
        ipo_rows = []
        for item in fetched_ipos:
            code = item.get("code", "")
            name = item.get("name", "")
            sub_price = item.get("subscription_price", 0)
            market_price = item.get("market_ref_price", 0)
            spread_pct = item.get("spread_pct", 0)
            start_date = item.get("start_date", "")
            end_date = item.get("end_date", "")
            listing = item.get("listing_date", "—")
            rec = item.get("recommendation", "—")

            # 建議圖示
            if "值得" in rec:
                rec = f"🟢 {rec}"
            elif "小利" in rec:
                rec = f"🟡 {rec}"
            elif "破發" in rec:
                rec = f"🔴 {rec}"

            ipo_rows.append({
                "代碼": code,
                "名稱": name,
                "承銷價": sub_price,
                "市價": market_price,
                "價差%": spread_pct,
                "申購起日": start_date,
                "申購迄日": end_date,
                "掛牌日": listing,
                "建議": rec,
            })

        df_ipo = pd.DataFrame(ipo_rows)
        st.dataframe(
            df_ipo,
            use_container_width=True,
            hide_index=True,
            column_config={
                "承銷價": st.column_config.NumberColumn(format="$%.1f"),
                "市價": st.column_config.NumberColumn(format="$%.1f"),
                "價差%": st.column_config.NumberColumn(format="%+.1f%%"),
            },
        )

        # 統計卡片
        total = len(ipo_rows)
        good_spread = len([r for r in ipo_rows if r["價差%"] > 20])
        cols = st.columns(3)
        with cols[0]:
            st.markdown(metric_card("可申購", str(total), status="positive" if total > 0 else "neutral"), unsafe_allow_html=True)
        with cols[1]:
            st.markdown(metric_card("價差>20%", str(good_spread), status="positive" if good_spread > 0 else "neutral"), unsafe_allow_html=True)
        with cols[2]:
            avg_spread = sum(r["價差%"] for r in ipo_rows) / total if total else 0
            st.markdown(metric_card("平均價差", f"{avg_spread:+.1f}%",
                        status="positive" if avg_spread > 0 else "negative"), unsafe_allow_html=True)

        st.caption(f"共 {total} 筆可申購，資料來源：Histock（每小時更新）。已截止的申購自動隱藏。")
    else:
        st.info("目前無可申購的 IPO。可使用下方手動新增。")

    with st.expander("➕ 手動新增申購候選", expanded=False):
        with st.form("add_ipo_candidate"):
            col1, col2 = st.columns(2)
            with col1:
                ipo_code = st.text_input("股票代碼", placeholder="例：6951")
                ipo_name = st.text_input("公司名稱", placeholder="例：創新科技")
                ipo_price = st.number_input("承銷價（元）", min_value=1.0, step=0.5, value=100.0)
            with col2:
                ipo_start = st.date_input("申購起日", value=date.today())
                ipo_end = st.date_input("申購迄日", value=date.today())
            submitted = st.form_submit_button("新增")
            if submitted:
                if not ipo_code or not ipo_name:
                    st.error("代碼與名稱為必填欄位。")
                else:
                    candidates: list[dict] = st.session_state.get("ipo_candidates", [])
                    candidates.append({
                        "code": ipo_code.strip(),
                        "name": ipo_name.strip(),
                        "subscription_price": float(ipo_price),
                        "start_date": str(ipo_start),
                        "end_date": str(ipo_end),
                    })
                    st.session_state["ipo_candidates"] = candidates
                    st.success(f"已新增 {ipo_code} {ipo_name}")
                    st.rerun()

    candidates: list[dict] = st.session_state.get("ipo_candidates", [])
    if candidates:
        rows = []
        for entry in candidates:
            code = entry["code"]
            quote = fetch_stock_quote(code)
            current_price = quote.get("price", 0)
            sub_price = entry["subscription_price"]
            spread_pct = ((current_price - sub_price) / sub_price * 100) if sub_price and current_price else None
            rows.append({
                "代碼": code,
                "名稱": entry["name"],
                "承銷價": sub_price,
                "現價": current_price if current_price else "—",
                "價差%": spread_pct,
                "申購起日": entry["start_date"],
                "申購迄日": entry["end_date"],
            })
        df_candidates = pd.DataFrame(rows)
        st.dataframe(
            df_candidates,
            width="stretch",
            hide_index=True,
            column_config={
                "價差%": st.column_config.NumberColumn(format="+%.1f%%"),
            },
        )

        # remove button
        to_remove = st.selectbox(
            "移除申購候選",
            options=["— 選擇 —"] + [f"{e['code']} {e['name']}" for e in candidates],
        )
        if st.button("移除", key="remove_candidate") and to_remove != "— 選擇 —":
            rm_code = to_remove.split(" ")[0]
            st.session_state["ipo_candidates"] = [
                e for e in candidates if e["code"] != rm_code
            ]
            st.rerun()
    else:
        st.caption("尚無申購候選資料，請使用上方表單新增。")

    # ── 蜜月期追蹤 ──────────────────────────────
    st.divider()
    st.subheader("蜜月期追蹤（上市 30 日內）")

    with st.expander("➕ 新增追蹤", expanded=False):
        with st.form("add_honeymoon"):
            hm_col1, hm_col2 = st.columns(2)
            with hm_col1:
                hm_code = st.text_input("股票代碼", placeholder="例：6948", key="hm_code")
                hm_name = st.text_input("公司名稱", placeholder="例：先進半導", key="hm_name")
            with hm_col2:
                hm_listing = st.date_input("上市日期", value=date.today(), key="hm_listing")
                hm_sub_price = st.number_input(
                    "承銷價（元）", min_value=1.0, step=0.5, value=100.0, key="hm_sub_price"
                )
            hm_submitted = st.form_submit_button("新增追蹤")
            if hm_submitted:
                if not hm_code or not hm_name:
                    st.error("代碼與名稱為必填欄位。")
                else:
                    honeymoon: list[dict] = st.session_state.get("ipo_honeymoon", [])
                    honeymoon.append({
                        "code": hm_code.strip(),
                        "name": hm_name.strip(),
                        "listing_date": str(hm_listing),
                        "subscription_price": float(hm_sub_price),
                    })
                    st.session_state["ipo_honeymoon"] = honeymoon
                    st.success(f"已新增蜜月追蹤：{hm_code} {hm_name}")
                    st.rerun()

    honeymoon: list[dict] = st.session_state.get("ipo_honeymoon", [])
    if honeymoon:
        hm_rows = []
        for entry in honeymoon:
            code = entry["code"]
            quote = fetch_stock_quote(code)
            current_price = quote.get("price", 0)
            sub_price = entry["subscription_price"]
            listing_date = datetime.strptime(entry["listing_date"], "%Y-%m-%d").date()
            days_since = (date.today() - listing_date).days
            return_pct = (
                (current_price - sub_price) / sub_price * 100
                if sub_price and current_price
                else None
            )
            status = "🔴 蜜月結束" if days_since > 30 else "🟢 追蹤中"
            hm_rows.append({
                "代碼": code,
                "名稱": entry["name"],
                "上市日": entry["listing_date"],
                "承銷價": sub_price,
                "現價": current_price if current_price else "—",
                "報酬%": return_pct,
                "上市天數": days_since,
                "狀態": status,
            })
        hm_df = pd.DataFrame(hm_rows)
        st.dataframe(
            hm_df,
            width="stretch",
            hide_index=True,
            column_config={
                "報酬%": st.column_config.NumberColumn(format="%+.1f%%"),
            },
        )

        hm_remove = st.selectbox(
            "移除追蹤標的",
            options=["— 選擇 —"] + [f"{e['code']} {e['name']}" for e in honeymoon],
        )
        if st.button("移除", key="remove_honeymoon") and hm_remove != "— 選擇 —":
            rm_code = hm_remove.split(" ")[0]
            st.session_state["ipo_honeymoon"] = [
                e for e in honeymoon if e["code"] != rm_code
            ]
            st.rerun()
    else:
        st.info("尚無蜜月期追蹤標的，請使用上方「新增追蹤」表單加入。")

    # ── 歷史勝率 ────────────────────────────────
    st.divider()
    col_a, col_b = st.columns(2)

    history: list[dict] = st.session_state.get("ipo_history", [])

    with col_a:
        st.subheader("歷史勝率統計")
        if not history:
            st.info("尚無歷史 IPO 紀錄。待追蹤標的蜜月期結束後，可手動歸檔至歷史。")
        else:
            total = len(history)
            wins = [h for h in history if (h.get("return_pct") or 0) > 0]
            win_rate = len(wins) / total * 100 if total else 0
            returns = [h.get("return_pct") or 0 for h in history]
            avg_ret = sum(returns) / len(returns) if returns else 0
            max_ret = max(returns) if returns else 0

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(metric_card("總申購", str(total), status="neutral"), unsafe_allow_html=True)
                st.markdown(
                    metric_card("勝率(30日)", f"{win_rate:.1f}%", status="positive" if win_rate >= 50 else "negative"),
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    metric_card("平均報酬", f"{avg_ret:+.1f}%", status="positive" if avg_ret >= 0 else "negative"),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    metric_card("最大報酬", f"{max_ret:+.1f}%", status="positive"),
                    unsafe_allow_html=True,
                )

    with col_b:
        st.subheader("IPO 報酬分佈")
        if not history:
            st.caption("尚無歷史資料可繪圖。")
        else:
            # group by month
            monthly: dict[str, list[float]] = {}
            for h in history:
                month = str(h.get("listing_date", ""))[:7]
                if month:
                    monthly.setdefault(month, []).append(h.get("return_pct") or 0)
            months = sorted(monthly.keys())
            avg_by_month = [sum(monthly[m]) / len(monthly[m]) for m in months]
            if months:
                fig = bar_chart(months, avg_by_month, title="月平均報酬%", color_by_value=True, height=350)
                st.plotly_chart(fig, width="stretch")
