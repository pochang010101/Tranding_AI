"""P-11 系統設定 — API 金鑰、推播通道、風控參數、選股參數、系統資訊。"""

from __future__ import annotations

import os
import sys

import streamlit as st

from atlas.presentation.components.theme import get_colors, metric_card


def render() -> None:
    st.title("⚙️ 系統設定")
    st.markdown("""
<div class="legend-box">
<strong>欄位說明</strong><br>
📌 <strong>各設定項</strong>：調整系統參數，包含通知管道、API Key、交易偏好等，分頁管理不同類型設定。<br>
⚡ <strong>即時生效</strong>：部分設定（如風控參數、選股參數）修改後按「儲存」即生效，無需重啟服務。<br>
🔒 <strong>敏感資訊</strong>：API Key、Webhook URL、資料庫連線字串以遮罩顯示，實際值請透過環境變數或 .env 設定。
</div>
""", unsafe_allow_html=True)
    get_colors()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔑 API 金鑰", "📢 推播通道", "🛡️ 風控參數", "📊 選股參數", "🖥️ 系統資訊",
    ])

    # ── API 金鑰 ────────────────────────────────
    with tab1:
        st.subheader("資料源 API")
        st.text_input("TWSE API Token", type="password",
                     value=os.getenv("TWSE_API_TOKEN", ""),
                     placeholder="（免費，可留空）")
        st.text_input("yFinance Proxy", value=os.getenv("YFINANCE_PROXY", ""),
                     placeholder="（選填）")
        st.divider()
        st.subheader("推播 API")
        st.text_input("Discord Webhook URL", type="password",
                     value=os.getenv("DISCORD_WEBHOOK_URL", ""),
                     placeholder="https://discord.com/api/webhooks/...")
        st.text_input("LINE Channel Token", type="password",
                     value=os.getenv("LINE_CHANNEL_TOKEN", ""))
        st.text_input("Telegram Bot Token", type="password",
                     value=os.getenv("TELEGRAM_BOT_TOKEN", ""))
        st.text_input("Telegram Chat ID",
                     value=os.getenv("TELEGRAM_CHAT_ID", ""))
        st.divider()
        st.subheader("資料庫")
        db_url = os.getenv("ATLAS_DATABASE_URL", "")
        st.text_input("PostgreSQL URL", type="password",
                     value="***已設定***" if db_url else "",
                     placeholder="postgresql+asyncpg://...")
        redis_host = os.getenv("ATLAS_REDIS_HOST", "")
        st.text_input("Redis Host",
                     value=redis_host or "localhost",
                     placeholder="redis://localhost:6379/0")

        st.info("⚠️ API 金鑰請透過環境變數或 .env 檔案設定，此頁面僅供確認。")

    # ── 推播通道 ────────────────────────────────
    with tab2:
        st.subheader("通道啟用")
        ch_col1, ch_col2 = st.columns(2)

        # 從環境變數判斷哪些通道已設定
        discord_ok = bool(os.getenv("DISCORD_WEBHOOK_URL"))
        line_ok = bool(os.getenv("LINE_CHANNEL_TOKEN"))
        telegram_ok = bool(os.getenv("TELEGRAM_BOT_TOKEN"))

        with ch_col1:
            st.checkbox("Discord", value=discord_ok,
                       help="✅ 已設定" if discord_ok else "❌ 未設定 DISCORD_WEBHOOK_URL")
            st.checkbox("LINE", value=line_ok,
                       help="✅ 已設定" if line_ok else "❌ 未設定 LINE_CHANNEL_TOKEN")
        with ch_col2:
            st.checkbox("Telegram", value=telegram_ok,
                       help="✅ 已設定" if telegram_ok else "❌ 未設定 TELEGRAM_BOT_TOKEN")
            st.checkbox("Email", value=False, help="需設定 SMTP")

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

        st.divider()
        st.subheader("推播測試")
        test_channel = st.selectbox("測試通道", ["Discord", "LINE", "Telegram"])
        test_msg = st.text_input("測試訊息", value="Atlas v5.0 通知測試")
        if st.button("📤 發送測試訊息", type="primary", width="stretch"):
            st.info(f"正在發送至 {test_channel}...")
            try:
                if test_channel == "Discord" and discord_ok:
                    import httpx
                    webhook = os.getenv("DISCORD_WEBHOOK_URL")
                    resp = httpx.post(webhook, json={"content": test_msg}, timeout=10)
                    if resp.status_code in (200, 204):
                        st.success("Discord 測試訊息發送成功！")
                    else:
                        st.error(f"Discord 回應：{resp.status_code}")
                elif test_channel == "Telegram" and telegram_ok:
                    import httpx
                    token = os.getenv("TELEGRAM_BOT_TOKEN")
                    chat_id = os.getenv("TELEGRAM_CHAT_ID")
                    if chat_id:
                        resp = httpx.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json={"chat_id": chat_id, "text": test_msg},
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            st.success("Telegram 測試訊息發送成功！")
                        else:
                            st.error(f"Telegram 回應：{resp.status_code}")
                    else:
                        st.warning("請設定 TELEGRAM_CHAT_ID 環境變數")
                else:
                    st.warning(f"{test_channel} 尚未設定 API 金鑰，請先至 API 金鑰頁設定。")
            except Exception as exc:
                st.error(f"發送失敗：{exc}")

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

        st.button("💾 儲存風控參數", type="primary", width="stretch")

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

        st.button("💾 儲存選股參數", type="primary", width="stretch")

    # ── 系統資訊 ────────────────────────────────
    with tab5:
        st.subheader("系統狀態")
        sys_col1, sys_col2 = st.columns(2)
        with sys_col1:
            py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            st.markdown(metric_card("Python", py_ver, status="neutral"),
                       unsafe_allow_html=True)
            try:
                import streamlit
                st_ver = streamlit.__version__
            except Exception:
                st_ver = "unknown"
            st.markdown(metric_card("Streamlit", st_ver, status="neutral"),
                       unsafe_allow_html=True)
            db_status = "🟢 已設定" if os.getenv("ATLAS_DATABASE_URL") else "🔴 未設定"
            st.markdown(metric_card("PostgreSQL", db_status,
                       status="positive" if "🟢" in db_status else "negative"),
                       unsafe_allow_html=True)
        with sys_col2:
            redis_status = "🟢 已設定" if os.getenv("ATLAS_REDIS_HOST") else "🟡 未設定"
            st.markdown(metric_card("Redis", redis_status, status="neutral"),
                       unsafe_allow_html=True)

            # Count actual Python modules
            import glob
            mod_count = len(glob.glob("atlas/**/*.py", recursive=True))
            st.markdown(metric_card("模組數", str(mod_count), status="neutral"),
                       unsafe_allow_html=True)
            st.markdown(metric_card("版本", "v5.0.0-alpha", status="neutral"),
                       unsafe_allow_html=True)

        st.divider()
        st.subheader("健康檢查")
        if st.button("🔍 執行健康檢查", width="stretch"):
            components_result = []

            # Check yfinance
            try:
                from atlas.presentation.service_container import fetch_stock_quote
                q = fetch_stock_quote("2330")
                price = q.get("price", 0)
                components_result.append(("yFinance", "🟢 OK" if price > 0 else "🟡 No Data", "—"))
            except Exception as e:
                components_result.append(("yFinance", f"🔴 {e}", "—"))

            # Check indicator lib
            try:
                from atlas.presentation.service_container import get_indicator_lib
                get_indicator_lib()
                components_result.append(("IndicatorLib", "🟢 OK", "—"))
            except Exception as e:
                components_result.append(("IndicatorLib", f"🔴 {e}", "—"))

            # Check SMC
            try:
                from atlas.presentation.service_container import get_smc_module
                get_smc_module()
                components_result.append(("SMC Module", "🟢 OK", "—"))
            except Exception as e:
                components_result.append(("SMC Module", f"🔴 {e}", "—"))

            # Check Monte Carlo
            try:
                from atlas.presentation.service_container import get_monte_carlo
                get_monte_carlo()
                components_result.append(("Monte Carlo", "🟢 OK", "—"))
            except Exception as e:
                components_result.append(("Monte Carlo", f"🔴 {e}", "—"))

            comp_df = {
                "組件": [c[0] for c in components_result],
                "狀態": [c[1] for c in components_result],
            }
            st.dataframe(comp_df, width="stretch", hide_index=True)
