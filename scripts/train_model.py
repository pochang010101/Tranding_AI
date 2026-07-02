"""Train ML model using historical stock data."""

import sys
sys.path.insert(0, ".")

from atlas.strategy.ml_engine import MLEngine
from atlas.strategy.indicator_lib import IndicatorLibrary
import yfinance as yf
import pandas as pd


def main():
    # Fetch training data for top stocks
    codes = ["2330.TW", "2454.TW", "2317.TW", "2308.TW", "2881.TW"]
    all_data = []

    lib = IndicatorLibrary()
    for code in codes:
        print(f"Fetching {code}...")
        ticker = yf.Ticker(code)
        df = ticker.history(period="2y")
        if df is not None and not df.empty:
            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            })
            df = lib.calculate_all(df)
            df["code"] = code
            all_data.append(df)
            print(f"  -> {len(df)} rows")

    if not all_data:
        print("No data fetched. Exiting.")
        sys.exit(1)

    combined = pd.concat(all_data, ignore_index=True)
    print(f"\nCombined dataset: {len(combined)} rows across {len(all_data)} stocks")

    engine = MLEngine()
    result = engine.train(combined)
    print(f"\nTraining result: {result}")

    import pathlib
    pathlib.Path("models").mkdir(exist_ok=True)
    engine.save_model("models/atlas_rf.joblib")
    print("Model saved to models/atlas_rf.joblib")

    print("\nFeature importance (top 10):")
    for feat, score in engine.feature_importance().items():
        print(f"  {feat}: {score:.4f}")


if __name__ == "__main__":
    main()
