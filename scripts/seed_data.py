"""Seed data — 初始化市場、產業、策略基礎資料。"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_URL = os.getenv(
    "ATLAS_DATABASE_URL",
    "postgresql+asyncpg://atlas:atlas_dev@localhost:5432/atlas",
)

# ── Seed Data ────────────────────────────────

MARKETS = [
    {"code": "TW", "name": "台灣證券交易所", "timezone": "Asia/Taipei",
     "currency": "TWD", "open_time": "09:00", "close_time": "13:30"},
    {"code": "US", "name": "美國證券交易所", "timezone": "America/New_York",
     "currency": "USD", "open_time": "09:30", "close_time": "16:00"},
]

TW_INDUSTRIES = [
    ("01", "水泥"), ("02", "食品"), ("03", "塑膠"), ("04", "紡織"),
    ("05", "電機機械"), ("06", "電器電纜"), ("08", "玻璃陶瓷"),
    ("09", "造紙"), ("10", "鋼鐵"), ("11", "橡膠"), ("12", "汽車"),
    ("14", "建材營造"), ("15", "航運"), ("16", "觀光"), ("17", "金融保險"),
    ("18", "貿易百貨"), ("20", "其他"), ("21", "化學工業"), ("22", "生技醫療"),
    ("23", "油電燃氣"), ("24", "半導體"), ("25", "電腦及週邊設備"),
    ("26", "光電"), ("27", "通信網路"), ("28", "電子零組件"),
    ("29", "電子通路"), ("30", "資訊服務"), ("31", "其他電子"),
    ("32", "文化創意"), ("33", "農業科技"), ("34", "電商"),
]

TW_TOP_STOCKS = [
    ("2330", "台積電", "24"), ("2454", "聯發科", "24"),
    ("2317", "鴻海", "28"), ("2308", "台達電", "28"),
    ("2881", "富邦金", "17"), ("2882", "國泰金", "17"),
    ("2891", "中信金", "17"), ("2303", "聯電", "24"),
    ("3711", "日月光投控", "24"), ("2412", "中華電", "27"),
    ("2886", "兆豐金", "17"), ("1301", "台塑", "03"),
    ("1303", "南亞", "03"), ("2002", "中鋼", "10"),
    ("2884", "玉山金", "17"), ("3008", "大立光", "26"),
    ("2382", "廣達", "25"), ("2357", "華碩", "25"),
    ("6505", "台塑化", "23"), ("2892", "第一金", "17"),
    ("1216", "統一", "02"), ("2207", "和泰車", "12"),
    ("5880", "合庫金", "17"), ("2603", "長榮", "15"),
    ("2880", "華南金", "17"), ("2885", "元大金", "17"),
    ("3045", "台灣大", "27"), ("2912", "統一超", "18"),
    ("2395", "研華", "25"), ("4904", "遠傳", "27"),
]

STRATEGIES = [
    ("O1_gap_up", "O_SERIES", "缺口突破策略"),
    ("O2_vol_breakout", "O_SERIES", "量價突破策略"),
    ("O3_ma_cross", "O_SERIES", "均線交叉策略"),
    ("S1_ob_entry", "S_SERIES", "Order Block 進場策略"),
    ("S2_fvg_fill", "S_SERIES", "FVG 回補策略"),
    ("S3_sweep_reversal", "S_SERIES", "Liquidity Sweep 反轉策略"),
    ("K1_22day", "K_SERIES", "22日K線策略"),
    ("K2_fibonacci", "K_SERIES", "費氏均線策略"),
    ("P1_rs_leader", "P_SERIES", "RS 強勢領先策略"),
    ("P2_industry_rotate", "P_SERIES", "產業輪動策略"),
    ("T1_ml_predict", "T_SERIES", "ML 預測策略"),
    ("SD1_vol_anomaly", "SD_SERIES", "量能異常偵測"),
]


async def seed() -> None:
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as sess:
        # Markets
        for m in MARKETS:
            params = {**m}
            params["open_time"] = time.fromisoformat(m["open_time"])
            params["close_time"] = time.fromisoformat(m["close_time"])
            await sess.execute(text("""
                INSERT INTO market (code, name, timezone, currency, open_time, close_time)
                VALUES (:code, :name, :timezone, :currency, :open_time, :close_time)
                ON CONFLICT (code) DO NOTHING
            """), params)
        await sess.commit()
        logger.info("Seeded %d markets", len(MARKETS))

        # Get market_id for TW
        result = await sess.execute(text("SELECT market_id FROM market WHERE code = 'TW'"))
        tw_market_id = result.scalar()

        # Industries
        for code, name in TW_INDUSTRIES:
            await sess.execute(text("""
                INSERT INTO industry (market_id, code, name)
                VALUES (:market_id, :code, :name)
                ON CONFLICT (market_id, code) DO NOTHING
            """), {"market_id": tw_market_id, "code": code, "name": name})
        await sess.commit()
        logger.info("Seeded %d TW industries", len(TW_INDUSTRIES))

        # Stocks
        for symbol, name, ind_code in TW_TOP_STOCKS:
            # Look up industry_id
            ind_result = await sess.execute(text(
                "SELECT industry_id FROM industry WHERE market_id = :mid AND code = :code"
            ), {"mid": tw_market_id, "code": ind_code})
            ind_id = ind_result.scalar()

            await sess.execute(text("""
                INSERT INTO stock (market_id, symbol, name, industry_id, listing_type)
                VALUES (:market_id, :symbol, :name, :industry_id, 'TSE')
                ON CONFLICT (market_id, symbol) DO NOTHING
            """), {
                "market_id": tw_market_id, "symbol": symbol,
                "name": name, "industry_id": ind_id,
            })
        await sess.commit()
        logger.info("Seeded %d TW stocks", len(TW_TOP_STOCKS))

        # Strategies
        for code, category, desc in STRATEGIES:
            await sess.execute(text("""
                INSERT INTO strategy (code, name, category, description, is_active)
                VALUES (:code, :code, :category, :description, true)
                ON CONFLICT (code) DO NOTHING
            """), {"code": code, "category": category, "description": desc})
        await sess.commit()
        logger.info("Seeded %d strategies", len(STRATEGIES))

    await engine.dispose()
    logger.info("Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
