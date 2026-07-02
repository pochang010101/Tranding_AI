"""導航側邊欄 — 頁面導航 + 市場切換 + 主題切換 + 語言切換。"""

from __future__ import annotations

import streamlit as st

from atlas.i18n import SUPPORTED_LANGS, get_lang, set_lang
from atlas.presentation.components.theme import toggle_theme

# 頁面定義：(key, icon, label)
PAGES = [
    ("dashboard",  "📊", "總覽儀表板"),
    ("premarket",  "🌏", "盤前分析"),
    ("radar",      "📡", "盤中雷達"),
    ("screener",   "🔍", "每日選股"),
    ("universe",   "🗂️", "選股池管理"),
    ("portfolio",  "💼", "持倉追蹤"),
    ("backtest",   "📈", "回測分析"),
    ("ipo",        "🆕", "IPO 申購"),
    ("industry",   "🏭", "產業分析"),
    ("scheduler",  "⏰", "排程管理"),
    ("settings",   "⚙️", "系統設定"),
    ("kline",      "🕯️", "K 線分析"),
    ("paper",      "📝", "紙上交易"),
]


def render_sidebar() -> str:
    """渲染側邊欄，回傳選中的頁面 key。"""
    with st.sidebar:
        st.markdown("## 🏛️ Atlas v5.0")
        st.caption("量化交易決策系統")

        st.divider()

        # 市場切換
        market = st.radio(
            "市場",
            ["TW 台股", "US 美股"],
            index=0 if st.session_state.get("market", "TW") == "TW" else 1,
            horizontal=True,
            key="market_radio",
        )
        st.session_state["market"] = "TW" if "TW" in market else "US"

        st.divider()

        # 頁面導航
        current = st.session_state.get("page", "dashboard")
        for key, icon, label in PAGES:
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{key}",
                width="stretch",
                type="primary" if current == key else "secondary",
            ):
                st.session_state["page"] = key
                st.rerun()

        st.divider()

        # 語言切換
        _LANG_LABELS = {"zh-TW": "繁中", "en": "English"}
        current_lang = get_lang()
        selected_lang = st.selectbox(
            "Language / 語言",
            options=SUPPORTED_LANGS,
            index=SUPPORTED_LANGS.index(current_lang),
            format_func=lambda x: _LANG_LABELS.get(x, x),
            key="lang_selectbox",
        )
        if selected_lang != current_lang:
            set_lang(selected_lang)
            st.rerun()

        # 主題切換
        theme_label = "🌙 深色" if st.session_state.get("theme", "dark") == "dark" else "☀️ 亮色"
        if st.button(f"切換至 {'☀️ 亮色' if theme_label.startswith('🌙') else '🌙 深色'}",
                      width="stretch"):
            toggle_theme()
            st.rerun()

        # 系統狀態
        st.divider()
        st.caption(f"市場：{st.session_state.get('market', 'TW')}")

        # 登入使用者 + 登出
        st.divider()
        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(f"👤 {st.session_state.get('username', 'guest')}")
        with col2:
            if st.button("登出", key="logout_btn"):
                from atlas.presentation.auth import logout
                logout()

    return st.session_state.get("page", "dashboard")
