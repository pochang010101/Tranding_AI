"""Atlas i18n — dict-based 多語系支援。

支援語言：
  zh-TW  繁體中文（預設）
  en     English

用法：
    from atlas.i18n import t, get_lang, set_lang

    t("nav.dashboard")           # 依 session_state["lang"] 翻譯
    t("nav.dashboard", "en")     # 強制指定語言
"""

from __future__ import annotations

SUPPORTED_LANGS: list[str] = ["zh-TW", "en"]
_DEFAULT_LANG = "zh-TW"

# 延遲載入，避免在非 Streamlit 環境（如 pytest）直接 import st
def _load_translations() -> dict[str, dict[str, str]]:
    from atlas.translations import ALL_TRANSLATIONS
    return ALL_TRANSLATIONS


_TRANSLATIONS: dict[str, dict[str, str]] | None = None


def _get_translations() -> dict[str, dict[str, str]]:
    global _TRANSLATIONS
    if _TRANSLATIONS is None:
        _TRANSLATIONS = _load_translations()
    return _TRANSLATIONS


def t(key: str, lang: str | None = None) -> str:
    """翻譯 key。找不到時回傳 key 本身。"""
    if lang is None:
        lang = get_lang()
    translations = _get_translations()
    lang_dict = translations.get(lang, translations.get(_DEFAULT_LANG, {}))
    return lang_dict.get(key, key)


def get_lang() -> str:
    """從 st.session_state 取得目前語言，預設 zh-TW。"""
    try:
        import streamlit as st
        return st.session_state.get("lang", _DEFAULT_LANG)
    except Exception:
        return _DEFAULT_LANG


def set_lang(lang: str) -> None:
    """設定語言到 st.session_state。"""
    if lang not in SUPPORTED_LANGS:
        raise ValueError(f"Unsupported language: {lang!r}. Supported: {SUPPORTED_LANGS}")
    try:
        import streamlit as st
        st.session_state["lang"] = lang
    except Exception:
        pass
