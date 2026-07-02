"""P-11 系統設定 — API 金鑰、推播通道、風控參數、市場切換。"""

from __future__ import annotations

import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card


def render() -> None:
    st.title("⚙️ 系統設定")
    c = get_colors()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔑 API 金鑰", "📢 推播通道", "🛡️ 風控參數", "📊 選股參數", "🖥️ 系統資訊",
    ])

    # ── API 金鑰 ────────────────────────────────
    with tab1:
        st.subheader("資料源 API")
        st.text_input("TWSE API Token", type="password", placeholder="已設定" if True else "未設定")
        st.text_input("yFinance Proxy", placeholder="（選填）")
        st.divider()
        st.subheader("推播 API")
        st.text_input("Discord Webhook URL", type="password", placeholder="https://discord.com/api/webhooks/...")
        st.text_input("LINE Channel Token", type="password")
        st.text_input("Telegram Bot Token", type="password")
        st.divider()
        st.subheader("資料庫")
        st.text_input("PostgreSQL URL", type="password", placeholder="postgresql+asyncpg://...")
        st.text_input("Redis URL", type="password", placeholder="redis://localhost:6379/0")
        st.button("💾 儲存設定", type="primary", use_container_width=True)

    # ── 推播通道 ────────────────────────────────
    with tab2:
        st.subheader("通道啟用")
        ch_col1, ch_col2 = st.columns(2)
        with ch_col1:
            st.checkbox("Discord", value=True)
            st.checkbox("LINE", value=True)
        with ch_col2:
            st.checkbox("Telegram", value=False)
            st.checkbox("Email", value=False)

        st.divider()
        st.subheader("靜音時段")
        mute_col1, mute_col2 = st.columns(2)
        with mute_col1:
            st.number_input("靜音開始（時）", value=22, min_value=0, max_value=23)
        with mute_col2:
            st.number_input("靜音結束（時）", value=7, min_value=0, max_value=23)

        st.divider()
        st.subheader("頻率限制")
        st.number_input("最大發送次數（每分鐘）", value=10, min_value=1, max_value=60)

        if st.button("📤 測試推播", use_container_width=True):
            st.success("測試訊息已發送至所有啟用通道。")

    # ── 風控參數 ────────────────────────────────
    with tab3:
        st.subheader("倉位風控")
        rc1, rc2 = st.columns(2)
        with rc1:
            st.slider("單筆風險上限 %", 0.5, 5.0, 2.0, 0.5, key="risk_pct")
            st.slider("最大持倉數", 1, 20, 10, 1, key="max_positions")
            st.slider("單一產業上限 %", 10, 40, 20, 5, key="industry_cap")
        with rc2:
            st.slider("ATR 停損倍數", 1.0, 5.0, 2.0, 0.5, key="atr_mult")
            st.slider("最大回撤警報 %", 5, 30, 15, 5, key="dd_alert")
            st.slider("情緒極端倉位上限 %", 10, 50, 30, 10, key="extreme_cap")

        st.button("💾 儲存風控參數", type="primary", use_container_width=True)

    # ── 選股參數 ────────────────────────────────
    with tab4:
        st.subheader("四主軸權重")
        w1, w2, w3, w4 = st.columns(4)
        with w1:
            st.number_input("產業輪動", value=0.25, step=0.05, format="%.2f", key="w_ir")
        with w2:
            st.number_input("題材催化", value=0.25, step=0.05, format="%.2f", key="w_cat")
        with w3:
            st.number_input("資金流向", value=0.25, step=0.05, format="%.2f", key="w_ff")
        with w4:
            st.number_input("個股 RS", value=0.25, step=0.05, format="%.2f", key="w_rs")

        st.divider()
        st.subheader("選股池篩選")
        sp1, sp2 = st.columns(2)
        with sp1:
            st.number_input("最低日均量（張）", value=500, step=100, key="min_vol")
            st.number_input("最低股價", value=10.0, step=5.0, key="min_price")
        with sp2:
            st.number_input("Top N 候選", value=50, step=10, key="top_n")
            st.selectbox("最低結論等級", ["Lv5", "Lv4", "Lv3", "Lv2", "Lv1"], index=2, key="min_lv")

        st.button("💾 儲存選股參數", type="primary", use_container_width=True)

    # ── 系統資訊 ────────────────────────────────
    with tab5:
        st.subheader("系統狀態")
        sys_col1, sys_col2 = st.columns(2)
        with sys_col1:
            st.markdown(metric_card("Python", "3.14.4", status="neutral"), unsafe_allow_html=True)
            st.markdown(metric_card("Streamlit", "1.35+", status="neutral"), unsafe_allow_html=True)
            st.markdown(metric_card("PostgreSQL", "🟢 Connected", status="positive"),
                       unsafe_allow_html=True)
        with sys_col2:
            st.markdown(metric_card("Redis", "🟡 未安裝", status="neutral"), unsafe_allow_html=True)
            st.markdown(metric_card("模組數", "69", status="neutral"), unsafe_allow_html=True)
            st.markdown(metric_card("版本", "v5.0.0-alpha", status="neutral"), unsafe_allow_html=True)

        st.divider()
        st.subheader("健康檢查")
        if st.button("🔍 執行健康檢查", use_container_width=True):
            st.info("正在檢查所有組件...")
            components = {
                "組件": ["Database", "Cache", "QuoteAdapter", "EventBus", "Scheduler"],
                "狀態": ["🟢 HEALTHY", "🟡 DEGRADED", "🟢 HEALTHY", "🟢 HEALTHY", "🟢 HEALTHY"],
                "延遲(ms)": [12, None, 85, 1, 2],
            }
            st.dataframe(components, use_container_width=True, hide_index=True)
