"""主題管理 — 深色/亮色主題 CSS + Plotly 配色。"""

from __future__ import annotations

import streamlit as st

# ── 色彩定義 ─────────────────────────────────────

DARK = {
    "bg_primary": "#0e1117",
    "bg_secondary": "#1a1d23",
    "bg_card": "#262730",
    "text_primary": "#fafafa",
    "text_secondary": "#b0b8c1",
    "accent": "#00d4aa",
    "accent_secondary": "#667eea",
    "positive": "#00c853",
    "negative": "#ff1744",
    "warning": "#ff9100",
    "neutral": "#78909c",
    "border": "#3a3f4b",
    "plotly_template": "plotly_dark",
    "plotly_bg": "#0e1117",
    "plotly_paper": "#1a1d23",
    "plotly_grid": "#2a2d35",
    "candle_up": "#00c853",
    "candle_down": "#ff1744",
}

LIGHT = {
    "bg_primary": "#ffffff",
    "bg_secondary": "#f5f7fa",
    "bg_card": "#ffffff",
    "text_primary": "#1a1a2e",
    "text_secondary": "#6b7280",
    "accent": "#0066ff",
    "accent_secondary": "#7c3aed",
    "positive": "#16a34a",
    "negative": "#dc2626",
    "warning": "#f59e0b",
    "neutral": "#9ca3af",
    "border": "#e5e7eb",
    "plotly_template": "plotly_white",
    "plotly_bg": "#ffffff",
    "plotly_paper": "#f5f7fa",
    "plotly_grid": "#e5e7eb",
    "candle_up": "#16a34a",
    "candle_down": "#dc2626",
}


def get_colors() -> dict[str, str]:
    """取得當前主題色彩。"""
    return DARK if st.session_state.get("theme", "dark") == "dark" else LIGHT


def toggle_theme() -> None:
    """切換主題。"""
    current = st.session_state.get("theme", "dark")
    st.session_state["theme"] = "light" if current == "dark" else "dark"


def inject_css() -> None:
    """注入主題 CSS。"""
    c = get_colors()
    st.markdown(f"""
    <style>
    /* 卡片容器 */
    .metric-card {{
        background: {c["bg_card"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 0.8rem;
    }}
    .metric-card h3 {{
        color: {c["text_secondary"]};
        font-size: 0.85rem;
        margin: 0 0 0.3rem 0;
        font-weight: 500;
    }}
    .metric-card .value {{
        font-size: 1.8rem;
        font-weight: 700;
        color: {c["text_primary"]};
    }}
    .metric-card .positive {{ color: {c["positive"]}; }}
    .metric-card .negative {{ color: {c["negative"]}; }}
    .metric-card .neutral  {{ color: {c["neutral"]}; }}

    /* 狀態標籤 */
    .badge {{
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }}
    .badge-bull {{ background: {c["positive"]}22; color: {c["positive"]}; }}
    .badge-bear {{ background: {c["negative"]}22; color: {c["negative"]}; }}
    .badge-range {{ background: {c["warning"]}22; color: {c["warning"]}; }}

    /* 表格 hover */
    .stDataFrame tbody tr:hover {{
        background: {c["bg_secondary"]} !important;
    }}

    /* 隱藏 Streamlit footer */
    footer {{ visibility: hidden; }}
    </style>
    """, unsafe_allow_html=True)


def metric_card(title: str, value: str, delta: str = "", status: str = "neutral") -> str:
    """產生指標卡片 HTML。"""
    c = get_colors()
    delta_html = f'<span class="{status}">{delta}</span>' if delta else ""
    return f"""
    <div class="metric-card">
        <h3>{title}</h3>
        <div class="value {status}">{value}</div>
        {delta_html}
    </div>
    """


def regime_badge(state: str) -> str:
    """大盤狀態標籤。"""
    mapping = {"BULL": "badge-bull", "BEAR": "badge-bear", "RANGE": "badge-range"}
    cls = mapping.get(state, "badge-range")
    return f'<span class="badge {cls}">{state}</span>'
