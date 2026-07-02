"""Unit tests for the ML training pipeline in MLEngine."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from atlas.strategy.ml_engine import MLEngine, _ENGINEERED_FEATURES


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data with realistic price motion."""
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    close = np.clip(close, 1.0, None)
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(1_000_000, 10_000_000, n).astype(float)
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    return _make_ohlcv(300)


@pytest.fixture
def small_df() -> pd.DataFrame:
    return _make_ohlcv(30)  # fewer than minimum 60 rows


@pytest.fixture
def trained_engine(ohlcv_df: pd.DataFrame) -> MLEngine:
    engine = MLEngine()
    engine.train(ohlcv_df)
    return engine


# ── Feature preparation ───────────────────────────────────────────────────────

class TestPrepareFeatures:
    def test_returns_dataframe(self, ohlcv_df):
        engine = MLEngine()
        result = engine._prepare_features(ohlcv_df)
        assert isinstance(result, pd.DataFrame)

    def test_contains_target_column(self, ohlcv_df):
        engine = MLEngine()
        result = engine._prepare_features(ohlcv_df)
        assert "target" in result.columns

    def test_target_is_binary(self, ohlcv_df):
        engine = MLEngine()
        result = engine._prepare_features(ohlcv_df)
        unique = set(result["target"].dropna().unique())
        assert unique <= {0, 1}

    def test_engineered_features_present(self, ohlcv_df):
        engine = MLEngine()
        result = engine._prepare_features(ohlcv_df)
        # At least the core engineered features should appear
        core = {"RSI14", "MACD_hist", "K9", "BB_pct", "ATR14_pct",
                "close_ma8", "close_ma21", "vol_ratio", "candle_body_pct"}
        present = core & set(result.columns)
        assert len(present) >= 6, f"Missing features: {core - present}"

    def test_no_future_column_leakage(self, ohlcv_df):
        """Engineered feature columns must not include the raw target shift."""
        engine = MLEngine()
        result = engine._prepare_features(ohlcv_df)
        forbidden = {"future_return", "next_close", "next_open"}
        assert not forbidden & set(result.columns)


# ── Train ─────────────────────────────────────────────────────────────────────

class TestTrain:
    def test_returns_dict_with_metrics(self, ohlcv_df):
        engine = MLEngine()
        result = engine.train(ohlcv_df)
        assert isinstance(result, dict)
        for key in ("accuracy", "precision", "recall", "f1", "n_samples"):
            assert key in result, f"Missing key: {key}"

    def test_metrics_in_valid_range(self, ohlcv_df):
        engine = MLEngine()
        result = engine.train(ohlcv_df)
        for key in ("accuracy", "precision", "recall", "f1"):
            assert 0.0 <= result[key] <= 1.0, f"{key}={result[key]} out of range"

    def test_feature_importance_in_result(self, ohlcv_df):
        engine = MLEngine()
        result = engine.train(ohlcv_df)
        assert "feature_importance" in result
        assert isinstance(result["feature_importance"], dict)
        assert len(result["feature_importance"]) > 0

    def test_insufficient_data_returns_zeros(self, small_df):
        engine = MLEngine()
        result = engine.train(small_df)
        assert result["accuracy"] == 0.0
        assert result["n_samples"] < 60

    def test_stores_standalone_model(self, ohlcv_df):
        engine = MLEngine()
        engine.train(ohlcv_df)
        assert engine._standalone_model is not None


# ── Predict ───────────────────────────────────────────────────────────────────

class TestPredict:
    def test_returns_series(self, trained_engine, ohlcv_df):
        preds = trained_engine.predict(ohlcv_df)
        assert isinstance(preds, pd.Series)

    def test_predictions_are_binary(self, trained_engine, ohlcv_df):
        preds = trained_engine.predict(ohlcv_df)
        unique = set(preds.unique())
        assert unique <= {0, 1}

    def test_prediction_length_matches_input(self, trained_engine, ohlcv_df):
        preds = trained_engine.predict(ohlcv_df)
        assert len(preds) == len(ohlcv_df)

    def test_predict_without_train_raises(self, ohlcv_df):
        engine = MLEngine()
        with pytest.raises(RuntimeError, match="No standalone model"):
            engine.predict(ohlcv_df)


# ── Evaluate ──────────────────────────────────────────────────────────────────

class TestEvaluate:
    def test_returns_all_metrics(self):
        engine = MLEngine()
        y_true = [1, 0, 1, 0, 1, 1, 0, 0]
        y_pred = [1, 0, 0, 0, 1, 1, 0, 1]
        result = engine.evaluate(y_true, y_pred)
        assert set(result.keys()) == {"accuracy", "precision", "recall", "f1"}

    def test_perfect_prediction(self):
        engine = MLEngine()
        y = [1, 0, 1, 1, 0]
        result = engine.evaluate(y, y)
        assert result["accuracy"] == 1.0
        assert result["f1"] == 1.0

    def test_all_wrong_prediction(self):
        engine = MLEngine()
        y_true = [1, 1, 1, 1]
        y_pred = [0, 0, 0, 0]
        result = engine.evaluate(y_true, y_pred)
        assert result["accuracy"] == 0.0

    def test_metrics_in_valid_range(self):
        engine = MLEngine()
        rng = np.random.default_rng(0)
        y_true = rng.integers(0, 2, 100).tolist()
        y_pred = rng.integers(0, 2, 100).tolist()
        result = engine.evaluate(y_true, y_pred)
        for val in result.values():
            assert 0.0 <= val <= 1.0


# ── Save / Load roundtrip ─────────────────────────────────────────────────────

class TestSaveLoad:
    def test_save_and_load_roundtrip(self, ohlcv_df):
        engine = MLEngine()
        engine.train(ohlcv_df)
        original_preds = engine.predict(ohlcv_df).tolist()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_model.joblib")
            engine.save_model(path)

            engine2 = MLEngine()
            engine2.load_model(path)
            loaded_preds = engine2.predict(ohlcv_df).tolist()

        assert original_preds == loaded_preds

    def test_save_without_model_raises(self):
        engine = MLEngine()
        with pytest.raises(RuntimeError, match="No standalone model"):
            engine.save_model("/tmp/should_not_exist.joblib")

    def test_load_nonexistent_raises(self):
        engine = MLEngine()
        with pytest.raises(Exception):
            engine.load_model("/tmp/this_file_does_not_exist_xyz.joblib")

    def test_loaded_model_predicts_binary(self, ohlcv_df):
        engine = MLEngine()
        engine.train(ohlcv_df)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "model.joblib")
            engine.save_model(path)
            engine2 = MLEngine()
            engine2.load_model(path)
            preds = engine2.predict(ohlcv_df)
        assert set(preds.unique()) <= {0, 1}


# ── Feature importance ────────────────────────────────────────────────────────

class TestFeatureImportance:
    def test_returns_dict(self, trained_engine):
        fi = trained_engine.feature_importance()
        assert isinstance(fi, dict)

    def test_scores_sum_to_approx_one(self, trained_engine):
        fi = trained_engine.feature_importance()
        total = sum(fi.values())
        assert abs(total - 1.0) < 1e-4

    def test_sorted_descending(self, trained_engine):
        fi = trained_engine.feature_importance()
        scores = list(fi.values())
        assert scores == sorted(scores, reverse=True)

    def test_without_model_raises(self):
        engine = MLEngine()
        with pytest.raises(RuntimeError, match="No standalone model"):
            engine.feature_importance()
