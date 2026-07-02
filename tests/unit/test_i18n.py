"""Unit tests for atlas.i18n."""

from __future__ import annotations

import importlib
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Stub streamlit so tests work outside a Streamlit runtime
# ---------------------------------------------------------------------------

def _make_st_stub(initial_lang: str = "zh-TW") -> types.ModuleType:
    """Build a minimal streamlit stub with session_state."""
    st = types.ModuleType("streamlit")
    st.session_state = {"lang": initial_lang}  # type: ignore[attr-defined]
    return st


@pytest.fixture(autouse=True)
def _isolate_i18n(monkeypatch):
    """Re-import atlas.i18n fresh for each test with a clean st stub."""
    # Install stub before import
    st_stub = _make_st_stub("zh-TW")
    monkeypatch.setitem(sys.modules, "streamlit", st_stub)

    # Force re-import so the module picks up the stub
    for mod in list(sys.modules):
        if mod.startswith("atlas.i18n") or mod == "atlas.i18n":
            monkeypatch.delitem(sys.modules, mod, raising=False)

    yield st_stub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTranslationFunction:
    def test_zh_tw_default_returns_chinese(self, _isolate_i18n):
        from atlas.i18n import t

        assert t("nav.dashboard", "zh-TW") == "總覽儀表板"
        assert t("trade.buy", "zh-TW") == "買入"
        assert t("status.loading", "zh-TW") == "載入中..."

    def test_en_returns_english(self, _isolate_i18n):
        from atlas.i18n import t

        assert t("nav.dashboard", "en") == "Dashboard"
        assert t("trade.buy", "en") == "Buy"
        assert t("status.loading", "en") == "Loading..."

    def test_missing_key_returns_key_itself(self, _isolate_i18n):
        from atlas.i18n import t

        assert t("nonexistent.key", "zh-TW") == "nonexistent.key"
        assert t("nonexistent.key", "en") == "nonexistent.key"

    def test_missing_key_no_crash(self, _isolate_i18n):
        from atlas.i18n import t

        result = t("totally.unknown.key.xyz")
        assert result == "totally.unknown.key.xyz"

    def test_unknown_lang_falls_back_to_zh_tw(self, _isolate_i18n):
        from atlas.i18n import t

        # Unknown lang → falls back to zh-TW dict
        result = t("nav.dashboard", "ja")
        assert result == "總覽儀表板"


class TestGetLang:
    def test_returns_session_state_lang(self, _isolate_i18n):
        import streamlit as st
        from atlas.i18n import get_lang

        st.session_state["lang"] = "en"
        assert get_lang() == "en"

    def test_defaults_to_zh_tw_when_missing(self, _isolate_i18n):
        import streamlit as st
        from atlas.i18n import get_lang

        st.session_state.pop("lang", None)
        assert get_lang() == "zh-TW"


class TestSetLang:
    def test_set_lang_updates_session_state(self, _isolate_i18n):
        import streamlit as st
        from atlas.i18n import set_lang

        set_lang("en")
        assert st.session_state.get("lang") == "en"

    def test_set_lang_back_to_zh_tw(self, _isolate_i18n):
        import streamlit as st
        from atlas.i18n import set_lang

        set_lang("en")
        set_lang("zh-TW")
        assert st.session_state.get("lang") == "zh-TW"

    def test_set_lang_unsupported_raises(self, _isolate_i18n):
        from atlas.i18n import set_lang

        with pytest.raises(ValueError, match="Unsupported language"):
            set_lang("ja")


class TestLangSwitchIntegration:
    def test_t_uses_get_lang_implicitly(self, _isolate_i18n):
        """t() without explicit lang should read from session_state."""
        import streamlit as st
        from atlas.i18n import t

        st.session_state["lang"] = "zh-TW"
        assert t("trade.sell") == "賣出"

        st.session_state["lang"] = "en"
        assert t("trade.sell") == "Sell"

    def test_all_zh_tw_keys_exist_in_en(self, _isolate_i18n):
        """Every zh-TW key must also exist in en translation."""
        from atlas.translations.zh_TW import TRANSLATIONS as ZH
        from atlas.translations.en import TRANSLATIONS as EN

        missing = [k for k in ZH if k not in EN]
        assert missing == [], f"Keys missing from en: {missing}"
