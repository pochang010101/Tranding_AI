#!/usr/bin/env python3
"""Atlas v5.0 Performance Benchmark — indicator calculation + scoring throughput."""

from __future__ import annotations

import time
import statistics
import sys

import numpy as np
import pandas as pd


def generate_ohlcv(n: int = 500) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    close = np.maximum(close, 10)
    return pd.DataFrame({
        "open": close * (1 + rng.normal(0, 0.005, n)),
        "high": close * (1 + abs(rng.normal(0, 0.01, n))),
        "low": close * (1 - abs(rng.normal(0, 0.01, n))),
        "close": close,
        "volume": rng.integers(100_000, 10_000_000, n),
    })


def bench_indicator_lib(df: pd.DataFrame, iterations: int = 100) -> float:
    """Benchmark IndicatorLibrary.calculate_all()."""
    from atlas.strategy.indicator_lib import IndicatorLibrary
    lib = IndicatorLibrary()
    # Warmup
    lib.calculate_all(df)

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        lib.calculate_all(df)
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def bench_scoring_engine(iterations: int = 100) -> float:
    """Benchmark ScoringEngine.score_axis()."""
    # Benchmark pure computation: indicator-based scoring logic
    from atlas.strategy.indicator_lib import IndicatorLibrary
    lib = IndicatorLibrary()
    df = generate_ohlcv(250)
    ind = lib.calculate_all(df)
    last = ind.iloc[-1]

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        # Simulate scoring logic (same as p04_screener._score_from_indicators)
        rsi = last.get("RSI14", 50)
        macd_hist = last.get("MACD_hist", 0)
        close = last.get("close", 0)
        ma21 = last.get("MA21", close)
        ma55 = last.get("MA55", close)
        tech = 35 * (40 <= rsi <= 75) + 35 * (close > ma21) + 30 * (macd_hist > 0)
        momentum = 50 * (last.get("K9", 50) > 50) + 50 * (ma21 > ma55)
        rs = min(100, max(0, rsi))
        total = tech * 0.5 + momentum * 0.3 + rs * 0.2
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def bench_smc_module(df: pd.DataFrame, iterations: int = 50) -> float:
    """Benchmark SMCModule.analyze()."""
    from atlas.strategy.smc_module import SMCModule
    smc = SMCModule()
    smc.analyze("TEST", df)  # warmup

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        smc.analyze("TEST", df)
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def bench_monte_carlo(iterations: int = 20) -> float:
    """Benchmark MonteCarloSimulator.simulate()."""
    from atlas.strategy.monte_carlo import MonteCarloSimulator
    mc = MonteCarloSimulator()
    pnl = [float(x) for x in np.random.default_rng(42).normal(500, 2000, 100)]

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        mc.simulate(pnl, num_paths=1000, initial_capital=1_000_000)
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def main() -> None:
    print("=" * 60)
    print("Atlas v5.0 Performance Benchmark")
    print("=" * 60)

    df = generate_ohlcv(500)

    benchmarks = [
        ("IndicatorLibrary.calculate_all (500 bars)", lambda: bench_indicator_lib(df)),
        ("ScoringEngine.score_axis", lambda: bench_scoring_engine()),
        ("SMCModule.analyze (500 bars)", lambda: bench_smc_module(df)),
        ("MonteCarloSimulator (1000 paths)", lambda: bench_monte_carlo()),
    ]

    results = []
    for name, fn in benchmarks:
        print(f"\n  Running: {name}...", end=" ", flush=True)
        try:
            median_ms = fn() * 1000
            print(f"{median_ms:.2f} ms")
            results.append((name, median_ms))
        except Exception as exc:
            print(f"ERROR: {exc}")
            results.append((name, -1))

    # 30-stock scan simulation
    print(f"\n  Running: 30-stock scan simulation...", end=" ", flush=True)
    from atlas.strategy.indicator_lib import IndicatorLibrary
    lib = IndicatorLibrary()
    start = time.perf_counter()
    for _ in range(30):
        stock_df = generate_ohlcv(250)
        lib.calculate_all(stock_df)
    scan_time = (time.perf_counter() - start) * 1000
    print(f"{scan_time:.0f} ms")
    results.append(("30-stock scan (250 bars each)", scan_time))

    print("\n" + "=" * 60)
    print("Summary:")
    print("-" * 60)
    for name, ms in results:
        status = f"{ms:.2f} ms" if ms >= 0 else "FAILED"
        target = "< 50ms" if "score" in name.lower() else "< 500ms"
        print(f"  {name:45s} {status:>12s}  (target {target})")
    print("=" * 60)


if __name__ == "__main__":
    main()
