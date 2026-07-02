"""Streamlit 主程式 — Atlas Trading System v5.0 Web UI 入口。"""

from __future__ import annotations

import streamlit as st


def _init_session() -> None:
    """初始化 session state。"""
    defaults = {
        "theme": "dark",
        "market": "TW",
        "page": "dashboard",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def main() -> None:
    """啟動 Streamlit 應用。"""
    st.set_page_config(
        page_title="Atlas v5.0 — 量化交易決策系統",
        page_icon="🏛️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _init_session()

    from atlas.presentation.components.theme import inject_css
    from atlas.presentation.components.sidebar import render_sidebar

    inject_css()
    page = render_sidebar()

    # 動態載入頁面
    page_map = {
        "dashboard":  "atlas.presentation.pages.p01_dashboard",
        "premarket":  "atlas.presentation.pages.p02_premarket",
        "radar":      "atlas.presentation.pages.p03_radar",
        "screener":   "atlas.presentation.pages.p04_screener",
        "universe":   "atlas.presentation.pages.p05_universe",
        "portfolio":  "atlas.presentation.pages.p06_portfolio",
        "backtest":   "atlas.presentation.pages.p07_backtest",
        "ipo":        "atlas.presentation.pages.p08_ipo",
        "industry":   "atlas.presentation.pages.p09_industry",
        "scheduler":  "atlas.presentation.pages.p10_scheduler",
        "settings":   "atlas.presentation.pages.p11_settings",
        "kline":      "atlas.presentation.pages.p12_kline",
    }

    module_path = page_map.get(page, page_map["dashboard"])
    try:
        import importlib
        mod = importlib.import_module(module_path)
        mod.render()
    except Exception as exc:
        st.error(f"頁面載入失敗：{exc}")
        st.info("請確認所有依賴模組已正確安裝。")


if __name__ == "__main__":
    main()
