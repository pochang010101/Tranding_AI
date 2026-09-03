"""P-17 籌碼分析 — 融資融券 + 借券 + 券資比 + 斷頭警戒。"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card

logger = logging.getLogger(__name__)


def _load_margin_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    """載入 TWSE + TPEx 融資融券全市場資料（快取 5 分鐘）。"""

    @st.cache_data(ttl=300)
    def _fetch() -> tuple[pd.DataFrame, pd.DataFrame]:
        from atlas.infrastructure.margin_data import (
            fetch_tpex_margin_all,
            fetch_twse_margin_all,
        )

        twse = fetch_twse_margin_all()
        tpex = fetch_tpex_margin_all()
        return twse, tpex

    return _fetch()


def _load_lending() -> pd.DataFrame:
    """載入借券賣出資料（快取 5 分鐘）。"""

    @st.cache_data(ttl=300)
    def _fetch() -> pd.DataFrame:
        from atlas.infrastructure.margin_data import fetch_twse_lending

        return fetch_twse_lending()

    return _fetch()


def _build_combined(twse: pd.DataFrame, tpex: pd.DataFrame) -> pd.DataFrame:
    """合併 TWSE + TPEx 並計算衍生欄位。"""
    if twse.empty and tpex.empty:
        return pd.DataFrame()
    combined = pd.concat([twse, tpex], ignore_index=True)
    # 計算融資增減 = 買進 - 賣出
    if "margin_buy" in combined.columns and "margin_sell" in combined.columns:
        combined["margin_change"] = combined["margin_buy"] - combined["margin_sell"]
    else:
        combined["margin_change"] = 0
    # 計算融券增減 = 賣出 - 買進
    if "short_sell" in combined.columns and "short_buy" in combined.columns:
        combined["short_change"] = combined["short_sell"] - combined["short_buy"]
    else:
        combined["short_change"] = 0
    # 券資比
    combined["short_margin_ratio"] = combined.apply(
        lambda r: (r["short_balance"] / r["margin_balance"] * 100)
        if r.get("margin_balance", 0) > 0
        else 0.0,
        axis=1,
    )
    # 融資增幅 %
    combined["margin_balance"] - combined["margin_change"]
    combined["margin_change_pct"] = combined.apply(
        lambda r: (
            r["margin_change"] / (r["margin_balance"] - r["margin_change"]) * 100
            if (r["margin_balance"] - r["margin_change"]) > 0
            else 0.0
        ),
        axis=1,
    )
    return combined


def _verdict_color(verdict: str) -> str:
    """根據判定結果返回 CSS class 名稱。"""
    mapping = {
        "bullish": "legend-good",
        "squeeze_alert": "legend-good",
        "bearish": "legend-bad",
        "margin_call_risk": "legend-bad",
        "neutral": "legend-warn",
    }
    return mapping.get(verdict, "legend-warn")


def _score_chip(row: pd.Series, flow: dict) -> tuple[int, str, list[str]]:
    """計算單檔籌碼綜合分數，回傳 (分數, 建議, 訊號列表)。

    分數 > 0 偏多，< 0 偏空，絕對值越大信號越強。
    """
    score = 0
    signals: list[str] = []

    sr_ratio = float(row.get("short_margin_ratio", 0))
    margin_chg = int(row.get("margin_change", 0))
    int(row.get("margin_balance", 0))
    float(row.get("margin_change_pct", 0))

    # 券資比（軋空潛力）
    if sr_ratio > 30:
        score += 30
        signals.append(f"券資比 {sr_ratio:.1f}%（軋空警戒）")
    elif sr_ratio > 20:
        score += 15
        signals.append(f"券資比 {sr_ratio:.1f}%（偏高）")
    elif sr_ratio < 3:
        score -= 10
        signals.append(f"券資比 {sr_ratio:.1f}%（極低）")

    # 融資增減（散戶動向，反指標）
    if margin_chg < -500:
        score += 20
        signals.append(f"融資大減 {margin_chg:+,} 張（籌碼洗清）")
    elif margin_chg < -100:
        score += 10
        signals.append(f"融資減少 {margin_chg:+,} 張")
    elif margin_chg > 1000:
        score -= 20
        signals.append(f"融資暴增 {margin_chg:+,} 張（散戶追高）")
    elif margin_chg > 300:
        score -= 10
        signals.append(f"融資增加 {margin_chg:+,} 張")

    # 法人買賣超
    total_net = flow.get("total_net", 0)
    foreign_net = flow.get("foreign_net", 0)
    if total_net > 3000:
        score += 25
        signals.append(f"法人大買 {total_net:+,} 張")
    elif total_net > 500:
        score += 10
        signals.append(f"法人買超 {total_net:+,} 張")
    elif total_net < -3000:
        score -= 25
        signals.append(f"法人大賣 {total_net:+,} 張")
    elif total_net < -500:
        score -= 10
        signals.append(f"法人賣超 {total_net:+,} 張")

    # 外資特別加分
    if foreign_net > 2000:
        score += 10
        signals.append(f"外資買超 {foreign_net:+,} 張")
    elif foreign_net < -2000:
        score -= 10
        signals.append(f"外資賣超 {foreign_net:+,} 張")

    # 判定建議
    if score >= 25:
        advice = "偏多"
    elif score >= 10:
        advice = "偏多觀察"
    elif score <= -25:
        advice = "偏空"
    elif score <= -10:
        advice = "偏空觀察"
    else:
        advice = "中性"

    return score, advice, signals


def _render_chip_recommendations(combined: pd.DataFrame, c: dict) -> None:
    """渲染籌碼選股建議區塊。"""
    from atlas.presentation.service_container import fetch_institutional_flow

    # 取每檔股票的法人資料（只對有 code 欄位的處理）
    if "code" not in combined.columns:
        st.info("資料格式不支援籌碼選股。")
        return

    # 排除成交量太小的（融資餘額 < 100 張）
    valid = combined[combined["margin_balance"] >= 100].copy()
    if valid.empty:
        st.info("無符合條件的股票。")
        return

    results = []
    # 批次取法人資料（用前 50 檔有意義的）
    candidates = valid.nlargest(50, "margin_balance")

    progress = st.progress(0, text="正在分析籌碼...")
    for i, (_, row) in enumerate(candidates.iterrows()):
        code = str(row["code"]).strip()
        if not code:
            continue
        try:
            flow = fetch_institutional_flow(code, days=1)
        except Exception:
            flow = {"foreign_net": 0, "trust_net": 0, "dealer_net": 0, "total_net": 0}

        score, advice, signals = _score_chip(row, flow)
        results.append({
            "代碼": code,
            "名稱": str(row.get("name", "")),
            "籌碼分數": score,
            "建議": advice,
            "券資比%": round(float(row.get("short_margin_ratio", 0)), 2),
            "融資增減": int(row.get("margin_change", 0)),
            "法人合計": flow.get("total_net", 0),
            "外資": flow.get("foreign_net", 0),
            "投信": flow.get("trust_net", 0),
            "訊號": " | ".join(signals),
        })
        progress.progress((i + 1) / len(candidates), text=f"分析中 {i+1}/{len(candidates)}...")

    progress.empty()

    if not results:
        st.info("無分析結果。")
        return

    result_df = pd.DataFrame(results).sort_values("籌碼分數", ascending=False)

    # 偏多 Top 10
    bullish = result_df[result_df["籌碼分數"] > 0].head(10)
    bearish = result_df[result_df["籌碼分數"] < 0].head(10)

    col_bull, col_bear = st.columns(2)

    with col_bull, st.container(border=True):
        st.markdown(
            f"#### <span style='color:{c.get('positive', 'green')}'>偏多建議 "
            f"Top {len(bullish)}</span>",
            unsafe_allow_html=True,
        )
        if bullish.empty:
            st.info("目前無偏多訊號股票")
        else:
            st.dataframe(
                bullish[["代碼", "名稱", "籌碼分數", "建議", "券資比%",
                         "融資增減", "法人合計", "外資"]],
                hide_index=True, width="stretch",
                column_config={
                    "籌碼分數": st.column_config.ProgressColumn(
                        min_value=-80, max_value=80, format="%d",
                    ),
                },
            )
            st.caption("偏多邏輯：券資比高(軋空) + 融資減少(洗清) + 法人買超")

    with col_bear, st.container(border=True):
        st.markdown(
            f"#### <span style='color:{c.get('negative', 'red')}'>偏空警示 "
            f"Top {len(bearish)}</span>",
            unsafe_allow_html=True,
        )
        if bearish.empty:
            st.info("目前無偏空訊號股票")
        else:
            bear_show = bearish.sort_values("籌碼分數").head(10)
            st.dataframe(
                bear_show[["代碼", "名稱", "籌碼分數", "建議", "券資比%",
                           "融資增減", "法人合計", "外資"]],
                hide_index=True, width="stretch",
                column_config={
                    "籌碼分數": st.column_config.ProgressColumn(
                        min_value=-80, max_value=80, format="%d",
                    ),
                },
            )
            st.caption("偏空邏輯：融資暴增(散戶追高) + 券資比低 + 法人賣超")

    # 詳細訊號展開
    with st.expander("展開完整訊號明細（全部 50 檔）"):
        st.dataframe(
            result_df[["代碼", "名稱", "籌碼分數", "建議", "訊號"]],
            hide_index=True, width="stretch", height=500,
        )

    # 加入觀察股按鈕
    st.divider()
    col_add1, col_add2, col_add3 = st.columns(3)
    with col_add1:
        if not bullish.empty:  # noqa: SIM102
            if st.button("將偏多股加入觀察股", type="primary", width="stretch"):
                codes = bullish["代碼"].tolist()
                existing = st.session_state.get("watchlist_codes", [])
                merged = list(dict.fromkeys(existing + codes))
                st.session_state["watchlist_codes"] = merged
                st.success(f"已加入 {len(codes)} 檔偏多股至觀察股")
    with col_add2:
        if not bearish.empty and st.button("將偏空股加入觀察股", width="stretch"):
            codes = bearish.sort_values("籌碼分數").head(10)["代碼"].tolist()
            existing = st.session_state.get("watchlist_codes", [])
            merged = list(dict.fromkeys(existing + codes))
            st.session_state["watchlist_codes"] = merged
            st.success(f"已加入 {len(codes)} 檔偏空股至觀察股")
    with col_add3:
        if st.button("前往盤中雷達 →", width="stretch"):
            st.session_state["page"] = "radar"
            st.rerun()


def render() -> None:
    st.title("💰 籌碼分析")

    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
<span class="legend-good">融資使用率</span>：融資餘額/限額 — &lt;20% 低檔有空間、&gt;60% 過熱警戒<br>
<span class="legend-warn">券資比</span>：融券餘額/融資餘額 — &gt;30% 軋空潛力、&lt;5% 散戶偏多<br>
<span class="legend-bad">融資維持率</span>：(股價×張數)/融資金額 — &lt;130% 斷頭線<br>
<span class="legend-good">借券賣出</span>：法人放空部位 — 大降=法人回補、持續增=法人看空
</div>
""", unsafe_allow_html=True)

    c = get_colors()

    # ── 全市場融資水位 ──
    st.divider()
    st.subheader("全市場融資水位")

    try:
        with st.spinner("載入融資融券資料..."):
            twse_df, tpex_df = _load_margin_all()
            combined = _build_combined(twse_df, tpex_df)
    except Exception as exc:
        logger.warning("載入融資融券資料失敗: %s", exc)
        st.warning(f"融資融券資料載入失敗：{exc}")
        combined = pd.DataFrame()

    if combined.empty:
        st.info("目前無可用的融資融券資料（可能為非交易時段）。")
    else:
        total_margin = int(combined["margin_balance"].sum())
        total_short = int(combined["short_balance"].sum())
        total_margin_chg = int(combined["margin_change"].sum())
        market_ratio = (total_short / total_margin * 100) if total_margin > 0 else 0.0

        cols = st.columns(4)
        with cols[0]:
            st.markdown(metric_card(
                "全市場融資餘額", f"{total_margin:,.0f} 張",
                status="neutral",
            ), unsafe_allow_html=True)
        with cols[1]:
            st.markdown(metric_card(
                "全市場融券餘額", f"{total_short:,.0f} 張",
                status="neutral",
            ), unsafe_allow_html=True)
        with cols[2]:
            ratio_status = "positive" if market_ratio > 20 else "neutral"
            st.markdown(metric_card(
                "全市場券資比", f"{market_ratio:.2f}%",
                status=ratio_status,
            ), unsafe_allow_html=True)
        with cols[3]:
            chg_status = (
                "positive" if total_margin_chg < -500
                else "negative" if total_margin_chg > 500
                else "neutral"
            )
            st.markdown(metric_card(
                "融資增減", f"{total_margin_chg:+,.0f} 張",
                status=chg_status,
            ), unsafe_allow_html=True)

    # ── 個股查詢 ──
    st.divider()
    st.subheader("個股查詢")

    col_input, col_btn = st.columns([3, 1])
    with col_input:
        stock_code = st.text_input("股票代碼", value="2330", key="margin_stock_code")
    with col_btn:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        query_clicked = st.button("查詢", key="margin_query_btn", type="primary")

    if query_clicked or stock_code:
        code = stock_code.strip()
        if not combined.empty and code:
            row = combined[combined["code"] == code]
            if row.empty:
                st.warning(f"找不到代碼 {code} 的融資融券資料。")
            else:
                row = row.iloc[0]

                # 借券資料
                lending_bal = 0
                try:
                    lending_df = _load_lending()
                    if not lending_df.empty:
                        lending_row = lending_df[lending_df["code"] == code]
                        if not lending_row.empty:
                            lending_bal = int(lending_row.iloc[0].get("lending_balance", 0))
                except Exception:
                    pass

                margin_bal = int(row.get("margin_balance", 0))
                margin_lim = int(row.get("margin_limit", 0))
                short_bal = int(row.get("short_balance", 0))
                short_lim = int(row.get("short_limit", 0))
                margin_chg = int(row.get("margin_change", 0))
                short_chg = int(row.get("short_change", 0))
                stock_name = str(row.get("name", code))

                margin_usage = (margin_bal / margin_lim * 100) if margin_lim > 0 else 0.0
                short_usage = (short_bal / short_lim * 100) if short_lim > 0 else 0.0
                sr_ratio = (short_bal / margin_bal * 100) if margin_bal > 0 else 0.0

                # 用 MarginAnalyzer 判定
                from atlas.domain.margin_analysis import MarginAnalyzer

                analyzer = MarginAnalyzer()
                signal = analyzer.analyze_single(
                    code=code,
                    name=stock_name,
                    margin_balance=margin_bal,
                    margin_limit=margin_lim,
                    short_balance=short_bal,
                    short_limit=short_lim,
                    lending_balance=lending_bal,
                    margin_change=margin_chg,
                    short_change=short_chg,
                )

                # 顯示指標卡片
                card_cols = st.columns(4)
                with card_cols[0]:
                    usage_status = (
                        "negative" if margin_usage > 60
                        else "positive" if margin_usage < 20
                        else "neutral"
                    )
                    st.markdown(metric_card(
                        f"{stock_name} 融資",
                        f"{margin_bal:,} / {margin_lim:,}",
                        delta=f"使用率 {margin_usage:.1f}%",
                        status=usage_status,
                    ), unsafe_allow_html=True)
                with card_cols[1]:
                    st.markdown(metric_card(
                        "融券",
                        f"{short_bal:,} / {short_lim:,}",
                        delta=f"使用率 {short_usage:.1f}%",
                        status="neutral",
                    ), unsafe_allow_html=True)
                with card_cols[2]:
                    sr_status = "positive" if sr_ratio > 30 else "neutral"
                    st.markdown(metric_card(
                        "券資比",
                        f"{sr_ratio:.2f}%",
                        status=sr_status,
                    ), unsafe_allow_html=True)
                with card_cols[3]:
                    st.markdown(metric_card(
                        "借券餘額",
                        f"{lending_bal:,} 張",
                        status="neutral",
                    ), unsafe_allow_html=True)

                # 判定結果
                verdict_cls = _verdict_color(signal.verdict)
                st.markdown(
                    f'<div class="legend-box">'
                    f'<strong>判定結果：</strong>'
                    f'<span class="{verdict_cls}">{signal.verdict.upper()}</span><br>'
                    f'{signal.detail}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        elif combined.empty:
            st.info("無融資融券資料可供查詢。")

    # ── 異常排行 ──
    if not combined.empty:
        st.divider()
        st.subheader("異常排行")

        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("**融資暴增 Top 10**")
            top_inc = combined.nlargest(10, "margin_change")[
                ["code", "name", "margin_change", "margin_balance", "margin_change_pct"]
            ].copy()
            top_inc.columns = ["代碼", "名稱", "融資增減", "融資餘額", "增幅%"]
            top_inc["增幅%"] = top_inc["增幅%"].round(2)
            st.dataframe(top_inc, hide_index=True, width="stretch")

        with col_right:
            st.markdown("**券資比 Top 10**")
            top_sr = combined.nlargest(10, "short_margin_ratio")[
                ["code", "name", "short_margin_ratio", "margin_balance", "short_balance"]
            ].copy()
            top_sr.columns = ["代碼", "名稱", "券資比%", "融資餘額", "融券餘額"]
            top_sr["券資比%"] = top_sr["券資比%"].round(2)
            st.dataframe(top_sr, hide_index=True, width="stretch")

        # ── 融資大減 Top 10 ──
        st.divider()
        st.subheader("融資大減 Top 10（籌碼洗清候選）")
        top_dec = combined.nsmallest(10, "margin_change")[
            ["code", "name", "margin_change", "margin_balance", "margin_change_pct"]
        ].copy()
        top_dec.columns = ["代碼", "名稱", "融資減少", "融資餘額", "減幅%"]
        top_dec["減幅%"] = top_dec["減幅%"].round(2)
        st.dataframe(top_dec, hide_index=True, width="stretch")

        # ── 借券賣出 Top 10 ──
        st.divider()
        st.subheader("借券賣出 Top 10")
        try:
            lending_df = _load_lending()
            if lending_df.empty:
                st.info("借券資料暫無法取得。")
            else:
                top_lending = lending_df.nlargest(10, "lending_balance")[
                    ["code", "name", "lending_balance", "lending_volume"]
                ].copy()
                top_lending.columns = ["代碼", "名稱", "借券賣出餘額", "當日借券賣出"]
                st.dataframe(top_lending, hide_index=True, width="stretch")
        except Exception as exc:
            logger.warning("借券資料載入失敗: %s", exc)
            st.warning(f"借券資料載入失敗：{exc}")

    # ══════════════════════════════════════════════════
    # 籌碼選股建議（真實資料 Top 10-20）
    # ══════════════════════════════════════════════════
    if not combined.empty:
        st.divider()
        st.subheader("📋 籌碼選股建議")
        st.markdown("""
<div class="legend-box">
<strong>選股邏輯說明</strong><br>
<span class="legend-good">偏多建議</span>：券資比 &gt;20% (軋空潛力) + 融資減少 (散戶出場)
+ 法人買超 → 籌碼集中，偏多操作<br>
<span class="legend-bad">偏空建議</span>：融資暴增 (散戶追高) + 券資比 &lt;5%
+ 法人賣超 → 籌碼凌亂，偏空觀望<br>
<span class="legend-warn">中性</span>：籌碼無明顯方向
</div>
""", unsafe_allow_html=True)

        try:
            _render_chip_recommendations(combined, c)
        except Exception as e:
            logger.warning("籌碼選股建議載入失敗: %s", e)
            st.warning(f"籌碼選股建議載入失敗：{e}")
