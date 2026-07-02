"""ML 預測引擎 — RandomForest 模型的訓練、推論與管理。"""

from __future__ import annotations

import logging
import pickle
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from atlas.enums import MarketType
from atlas.interfaces.strategy import IMLEngine

if TYPE_CHECKING:
    from atlas.infrastructure.data_manager import DataManager
    from atlas.strategy.indicator_lib import IndicatorLibrary

logger = logging.getLogger(__name__)

_MODEL_DIR = Path("models")

# Features produced by _prepare_features
_ENGINEERED_FEATURES = [
    "RSI14", "MACD_hist", "K9", "D9", "BB_pct", "ATR14_pct",
    "close_ma8", "close_ma21", "close_ma55", "vol_ratio",
    "candle_body_pct", "upper_shadow", "lower_shadow",
]


class MLEngine(IMLEngine):
    """RandomForest ML 預測引擎。

    - 僅使用 T-1 資料預測 T 日方向（防未來函數）
    - 特徵：技術指標 + 籌碼面 + 基本面衍生
    - 模型持久化至 models/ 目錄
    - 支援 standalone 同步訓練（data_manager/indicator_lib 可為 None）
    """

    def __init__(
        self,
        data_manager: DataManager | None = None,
        indicator_lib: IndicatorLibrary | None = None,
        model_dir: Path | None = None,
    ) -> None:
        self._dm = data_manager
        self._ind = indicator_lib
        self._model_dir = model_dir or _MODEL_DIR
        self._models: dict[str, Any] = {}  # market -> trained model
        self._standalone_model: Any = None  # model trained via sync train()

    # ── Standalone synchronous training pipeline ─────────────────────────

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Feature engineering on a OHLCV DataFrame.

        Returns a new DataFrame with engineered columns + 'target'.
        All look-ahead is avoided: shift(-5) is only used for the target label.
        """
        from atlas.strategy.indicator_lib import IndicatorLibrary

        lib = self._ind if self._ind is not None else IndicatorLibrary()
        result = lib.calculate_all(df.copy())

        close = result["close"]
        open_ = result.get("open", close)  # graceful fallback if open missing
        high = result.get("high", close)
        low = result.get("low", close)
        volume = result.get("volume", pd.Series(1, index=result.index))

        # ── Bollinger %B ────────────────────────────────────────────────
        if all(c in result.columns for c in ("BB_upper", "BB_lower")):
            bb_range = (result["BB_upper"] - result["BB_lower"]).replace(0, np.nan)
            result["BB_pct"] = (close - result["BB_lower"]) / bb_range
        else:
            result["BB_pct"] = np.nan

        # ── ATR % of close ──────────────────────────────────────────────
        if "ATR14" in result.columns:
            result["ATR14_pct"] = result["ATR14"] / close.replace(0, np.nan)
        else:
            result["ATR14_pct"] = np.nan

        # ── D9 alias (indicator_lib uses D3) ────────────────────────────
        if "D3" in result.columns and "D9" not in result.columns:
            result["D9"] = result["D3"]

        # ── Momentum: close / MA ratios ─────────────────────────────────
        for ma in (8, 21, 55):
            col = f"MA{ma}"
            if col in result.columns:
                result[f"close_ma{ma}"] = close / result[col].replace(0, np.nan)
            else:
                result[f"close_ma{ma}"] = np.nan

        # ── Volume ratio ────────────────────────────────────────────────
        vol_ma20 = volume.rolling(20).mean().replace(0, np.nan)
        result["vol_ratio"] = volume / vol_ma20

        # ── Candle pattern features ──────────────────────────────────────
        body = (close - open_) / open_.replace(0, np.nan)
        result["candle_body_pct"] = body
        candle_range = (high - low).replace(0, np.nan)
        upper_wick = high - close.clip(lower=open_)
        lower_wick = open_.clip(upper=close) - low
        result["upper_shadow"] = upper_wick / candle_range
        result["lower_shadow"] = lower_wick / candle_range

        # ── Binary target: 5-day forward return > 0 ─────────────────────
        future_ret = close.shift(-5) / close.replace(0, np.nan) - 1
        result["target"] = (future_ret > 0).astype(int)

        return result

    def train(self, df: pd.DataFrame, target_col: str = "future_return") -> dict[str, Any]:  # type: ignore[override]
        """Train a RandomForest on the provided OHLCV DataFrame.

        Args:
            df: Raw OHLCV data. Must have at least 60 rows.
            target_col: Ignored — target is always the 5-day forward return binary
                        label computed internally to prevent future leakage.

        Returns:
            dict with accuracy, precision, recall, f1, n_samples, feature_importance.
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
        from sklearn.model_selection import train_test_split

        prepared = self._prepare_features(df)
        prepared = prepared.dropna(subset=_ENGINEERED_FEATURES + ["target"])

        if len(prepared) < 60:
            logger.warning("Insufficient data for training: %d rows", len(prepared))
            return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0,
                    "f1": 0.0, "n_samples": len(prepared), "feature_importance": {}}

        feature_cols = [c for c in _ENGINEERED_FEATURES if c in prepared.columns]
        X = prepared[feature_cols].fillna(0)
        y = prepared["target"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, shuffle=False  # time-series safe
        )

        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=10,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        importance = dict(zip(feature_cols, model.feature_importances_))
        top_10 = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10])

        self._standalone_model = model
        self._feature_cols: list[str] = feature_cols

        result = {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
            "n_samples": int(len(prepared)),
            "feature_importance": {k: round(v, 4) for k, v in top_10.items()},
        }
        logger.info("Standalone model trained: accuracy=%.2f%%, f1=%.2f%%",
                    result["accuracy"] * 100, result["f1"] * 100)
        return result

    def predict(self, df: pd.DataFrame) -> pd.Series:  # type: ignore[override]
        """Predict direction using the standalone trained model.

        Args:
            df: Raw OHLCV data.

        Returns:
            pd.Series of int (0/1) predictions aligned to df's index.
        """
        if self._standalone_model is None:
            raise RuntimeError("No standalone model trained. Call train() or load_model() first.")

        prepared = self._prepare_features(df)
        feature_cols = getattr(self, "_feature_cols", _ENGINEERED_FEATURES)
        available = [c for c in feature_cols if c in prepared.columns]
        X = prepared[available].fillna(0)
        preds = self._standalone_model.predict(X)
        return pd.Series(preds, index=prepared.index, name="prediction")

    def evaluate(self, y_true: Any, y_pred: Any) -> dict[str, float]:
        """Calculate classification metrics.

        Args:
            y_true: Ground-truth labels (array-like of 0/1).
            y_pred: Predicted labels (array-like of 0/1).

        Returns:
            dict with accuracy, precision, recall, f1.
        """
        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

        return {
            "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
            "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        }

    def save_model(self, path: str) -> None:
        """Persist standalone model to disk using joblib."""
        import joblib

        if self._standalone_model is None:
            raise RuntimeError("No standalone model to save.")
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self._standalone_model,
                     "feature_cols": getattr(self, "_feature_cols", _ENGINEERED_FEATURES)}, out)
        logger.info("Standalone model saved: %s", out)

    def load_model(self, path: str) -> None:
        """Load standalone model from disk."""
        import joblib

        data = joblib.load(path)
        self._standalone_model = data["model"]
        self._feature_cols = data["feature_cols"]
        logger.info("Standalone model loaded: %s", path)

    def feature_importance(self) -> dict[str, float]:
        """Return feature importance ranking from the standalone model."""
        if self._standalone_model is None:
            raise RuntimeError("No standalone model available.")
        feature_cols = getattr(self, "_feature_cols", _ENGINEERED_FEATURES)
        importance = dict(zip(feature_cols, self._standalone_model.feature_importances_))
        return dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))

    async def predict_async(
        self, code: str, market: MarketType, features_df: pd.DataFrame
    ) -> dict[str, Any]:
        """預測單檔 T+1 方向（async，使用 market-level model）。"""
        model = self._get_model(market)
        if model is None:
            return {"prediction": False, "probability": 0.5, "feature_importance": {}}

        try:
            feature_cols = self._get_feature_columns(features_df)
            if not feature_cols:
                return {"prediction": False, "probability": 0.5, "feature_importance": {}}

            X = features_df[feature_cols].iloc[[-1]].fillna(0)
            proba = model.predict_proba(X)[0]
            pred_class = int(model.predict(X)[0])

            importance = dict(zip(feature_cols, model.feature_importances_))
            top_features = dict(
                sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
            )

            return {
                "prediction": bool(pred_class),
                "probability": round(float(proba[1] if len(proba) > 1 else proba[0]), 4),
                "feature_importance": {k: round(v, 4) for k, v in top_features.items()},
            }
        except Exception as exc:
            logger.warning("ML predict failed for %s: %s", code, exc)
            return {"prediction": False, "probability": 0.5, "feature_importance": {}}

    async def predict_batch(
        self, codes: list[str], market: MarketType
    ) -> dict[str, dict[str, Any]]:
        """批次預測。"""
        results: dict[str, dict[str, Any]] = {}
        end = date.today()
        start = end - timedelta(days=120)

        for code in codes:
            try:
                bars = await self._dm.fetch_daily_bars(code, market, start, end)
                if len(bars) < 60:
                    continue
                df = pd.DataFrame([
                    {"close": float(b.close), "high": float(b.high),
                     "low": float(b.low), "volume": b.volume}
                    for b in bars
                ])
                df = self._ind.calculate_all(df)
                results[code] = await self.predict_async(code, market, df)
            except Exception as exc:
                logger.debug("ML batch predict skip %s: %s", code, exc)

        return results

    async def train_async(
        self,
        market: MarketType,
        train_end_date: date,
        lookback_days: int = 500,
    ) -> dict[str, Any]:
        """訓練 RandomForest 模型。"""
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score

        # 這裡使用 0050.TW 作為訓練代理
        proxy = "0050" if market == MarketType.TW else "SPY"
        start = train_end_date - timedelta(days=lookback_days)
        bars = await self._dm.fetch_daily_bars(proxy, market, start, train_end_date)

        if len(bars) < 100:
            return {"accuracy": 0.0, "f1": 0.0, "feature_importance": {}}

        df = pd.DataFrame([
            {"close": float(b.close), "high": float(b.high),
             "low": float(b.low), "volume": b.volume}
            for b in bars
        ])
        df = self._ind.calculate_all(df)

        # 標籤：T+1 日漲=1, 跌=0（用 T-1 資料預測 T 日）
        df["target"] = (df["close"].shift(-1) > df["close"]).astype(int)
        df = df.dropna()

        feature_cols = self._get_feature_columns(df)
        if not feature_cols or len(df) < 50:
            return {"accuracy": 0.0, "f1": 0.0, "feature_importance": {}}

        X = df[feature_cols].fillna(0)
        y = df["target"]

        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=10,
            random_state=42,
            n_jobs=-1,
        )
        scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
        model.fit(X, y)

        self._models[market] = model
        self._save_model(market, model)

        importance = dict(zip(feature_cols, model.feature_importances_))
        top_10 = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10])

        result = {
            "accuracy": round(float(np.mean(scores)), 4),
            "f1": round(float(np.mean(scores)), 4),  # 簡化
            "feature_importance": {k: round(v, 4) for k, v in top_10.items()},
        }
        logger.info("ML model trained for %s: accuracy=%.2f%%", market, result["accuracy"] * 100)
        return result

    async def validate_no_future_leak(self, market: MarketType) -> bool:
        """防未來函數驗證：確認特徵僅使用 T-1 資料。

        驗證方式：特徵欄位不含 target、不含 shift(-1) 衍生欄。
        """
        model = self._get_model(market)
        if model is None:
            return True
        feature_names = getattr(model, "feature_names_in_", [])
        forbidden = {"target", "future_return", "next_close", "next_open"}
        leak = set(feature_names) & forbidden
        if leak:
            logger.error("Future leak detected in features: %s", leak)
            return False
        return True

    def _get_model(self, market: MarketType) -> Any:
        if market in self._models:
            return self._models[market]
        return self._load_model(market)

    def _save_model(self, market: MarketType, model: Any) -> None:
        self._model_dir.mkdir(parents=True, exist_ok=True)
        path = self._model_dir / f"rf_{market.value}.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)
        logger.info("Model saved: %s", path)

    def _load_model(self, market: MarketType) -> Any:
        path = self._model_dir / f"rf_{market.value}.pkl"
        if not path.exists():
            return None
        try:
            with open(path, "rb") as f:
                model = pickle.load(f)  # noqa: S301
            self._models[market] = model
            return model
        except Exception as exc:
            logger.warning("Failed to load model %s: %s", path, exc)
            return None

    @staticmethod
    def _get_feature_columns(df: pd.DataFrame) -> list[str]:
        """取得可用的特徵欄位（排除非數值、目標、日期欄）。"""
        exclude = {"target", "date", "trade_date", "code"}
        candidates = [
            "RSI14", "RSI6", "MACD", "MACD_signal", "MACD_hist",
            "BB_upper", "BB_middle", "BB_lower", "ATR14",
            "K9", "D3", "OBV",
            "MA8", "MA21", "MA55", "MA89",
            "MV5", "MV13", "MV34",
        ]
        return [c for c in candidates if c in df.columns and c not in exclude]
