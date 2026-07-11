"""Tests for theme_catalog — 題材概念股分類與熱度偵測。"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.strategy.theme_catalog import (
    THEME_MAP,
    ThemeHeat,
    detect_hot_themes,
    get_themes_for_code,
)


class TestThemeLookup:
    def test_tsmc_has_themes(self):
        themes = get_themes_for_code("2330")
        assert "AI" in themes
        assert "半導體" in themes

    def test_unknown_code_empty(self):
        assert get_themes_for_code("9999") == []

    def test_multiple_themes(self):
        themes = get_themes_for_code("3443")
        assert len(themes) >= 3  # AI, 半導體, CoWoS, 蘋果, etc.

    def test_theme_map_not_empty(self):
        assert len(THEME_MAP) >= 15


class TestDetectHotThemes:
    def test_basic_detection(self):
        df = pd.DataFrame([
            {"code": "2330", "name": "台積電", "change_pct": 3.0},
            {"code": "2454", "name": "聯發科", "change_pct": 2.5},
            {"code": "2382", "name": "廣達", "change_pct": 4.0},
            {"code": "2303", "name": "聯電", "change_pct": 1.5},
            {"code": "2881", "name": "富邦金", "change_pct": -0.5},
        ])
        results = detect_hot_themes(df)
        assert len(results) > 0
        assert results[0].heat_score >= results[-1].heat_score  # sorted

    def test_empty_df(self):
        assert detect_hot_themes(pd.DataFrame()) == []

    def test_theme_heat_fields(self):
        df = pd.DataFrame([
            {"code": "2330", "name": "台積電", "change_pct": 2.0},
            {"code": "2454", "name": "聯發科", "change_pct": 1.5},
        ])
        results = detect_hot_themes(df, top_n=5)
        for r in results:
            assert isinstance(r, ThemeHeat)
            assert r.stock_count > 0
            assert 0 <= r.heat_score <= 100

    def test_top_n_limit(self):
        df = pd.DataFrame([
            {"code": "2330", "name": "台積電", "change_pct": 2.0},
        ])
        results = detect_hot_themes(df, top_n=3)
        assert len(results) <= 3

    def test_negative_market(self):
        df = pd.DataFrame([
            {"code": "2330", "name": "台積電", "change_pct": -3.0},
            {"code": "2454", "name": "聯發科", "change_pct": -2.0},
            {"code": "2881", "name": "富邦金", "change_pct": -1.5},
        ])
        results = detect_hot_themes(df)
        # All themes should have low heat
        for r in results:
            assert r.avg_change_pct < 0
