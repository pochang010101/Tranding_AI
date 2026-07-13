"""導航 — 頂部水平選單 + 精簡側邊欄。"""

from __future__ import annotations

import streamlit as st

from atlas.presentation.components.theme import toggle_theme

# 頁面定義：(key, icon, label)
PAGES = [
    ("dashboard",     "📊", "總覽"),
    ("premarket",     "🌏", "盤前"),
    ("radar",         "📡", "雷達"),
    ("screener",      "🔍", "選股"),
    ("universe",      "🗂️", "股池"),
    ("backtest",      "📈", "回測"),
    ("ipo",           "🆕", "IPO"),
    ("industry",      "🏭", "產業"),
    ("kline",         "🕯️", "K線"),
    ("price_levels",  "📐", "價位"),
    ("smart_money",   "🏦", "主力"),
    ("factor_health", "🔬", "因子"),
    ("scheduler",     "⏰", "排程"),
    ("settings",      "⚙️", "設定"),
]


def render_sidebar() -> str:
    """渲染頂部導航 + 精簡側邊欄，回傳選中的頁面 key。"""

    # ── 精簡側邊欄：Logo + 市場 + 主題 + 使用者 ──
    with st.sidebar:
        st.markdown("## 🏛️ Atlas v5.0")
        st.caption("量化交易決策系統")
        st.divider()

        theme_label = "🌙 深色" if st.session_state.get("theme", "dark") == "dark" else "☀️ 亮色"
        if st.button(f"切換至 {'☀️ 亮色' if theme_label.startswith('🌙') else '🌙 深色'}",
                      width="stretch"):
            toggle_theme()
            st.rerun()

        st.divider()
        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(f"👤 {st.session_state.get('username', 'guest')}")
        with col2:
            if st.button("登出", key="logout_btn"):
                from atlas.presentation.auth import logout
                logout()

    # ── 頂部水平導航（使用 st.columns 模擬 pill 按鈕）──
    current = st.session_state.get("page", "dashboard")

    # 注入頂部導航 CSS
    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"].nav-bar button {
        font-size: 14px !important;
        padding: 6px 10px !important;
        min-height: 40px !important;
    }
    .nav-container {
        background: rgba(14,17,23,0.95);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 8px 10px;
        margin-bottom: 16px;
        border: 1px solid rgba(255,255,255,0.08);
        position: sticky;
        top: 0;
        z-index: 999;
    }
    /* Make Streamlit main container support sticky */
    [data-testid="stAppViewBlockContainer"] {
        overflow: visible !important;
    }
    header[data-testid="stHeader"] {
        z-index: 998 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="nav-container">', unsafe_allow_html=True)
    cols = st.columns(len(PAGES))
    for col, (key, icon, label) in zip(cols, PAGES):
        with col:
            btn_type = "primary" if current == key else "secondary"
            if st.button(f"{icon}{label}", key=f"nav_{key}", type=btn_type,
                         width="stretch"):
                st.session_state["page"] = key
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    return current
