"""持倉管理 — 追蹤部位狀態、損益計算與 R 倍數管理。"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from atlas.enums import MarketType
from atlas.interfaces.domain import IPortfolioManager

if TYPE_CHECKING:
    from atlas.infrastructure.data_manager import DataManager
    from atlas.strategy.indicator_lib import IndicatorLibrary

logger = logging.getLogger(__name__)


class _Position:
    __slots__ = (
        "journal_id", "code", "market", "entry_price", "shares",
        "stop_loss", "target_price", "entry_reason", "entry_date",
        "exit_price", "exit_date", "exit_reason", "is_open",
    )

    def __init__(
        self,
        journal_id: str,
        code: str,
        market: MarketType,
        entry_price: float,
        shares: int,
        stop_loss: float,
        target_price: float | None,
        entry_reason: str,
    ):
        self.journal_id = journal_id
        self.code = code
        self.market = market
        self.entry_price = entry_price
        self.shares = shares
        self.stop_loss = stop_loss
        self.target_price = target_price
        self.entry_reason = entry_reason
        self.entry_date = date.today()
        self.exit_price: float | None = None
        self.exit_date: date | None = None
        self.exit_reason: str = ""
        self.is_open = True


class PortfolioManager(IPortfolioManager):
    """持倉追蹤與 R 倍數管理。

    - 新增/平倉持倉
    - 即時未實現損益更新
    - ATR 動態倉位計算
    - 績效統計（勝率、期望值、平均 R）
    """

    def __init__(
        self,
        data_manager: DataManager | None = None,
        indicator_lib: IndicatorLibrary | None = None,
        initial_equity: float = 1_000_000,
    ) -> None:
        self._dm = data_manager
        self._ind = indicator_lib
        self._equity = initial_equity
        self._positions: dict[str, _Position] = {}
        self._closed: list[_Position] = []

    async def add_position(
        self,
        code: str,
        market: MarketType,
        entry_price: float,
        shares: int,
        stop_loss: float,
        target_price: float | None = None,
        entry_reason: str = "",
    ) -> str:
        journal_id = str(uuid.uuid4())[:8]
        pos = _Position(
            journal_id=journal_id,
            code=code,
            market=market,
            entry_price=entry_price,
            shares=shares,
            stop_loss=stop_loss,
            target_price=target_price,
            entry_reason=entry_reason,
        )
        self._positions[journal_id] = pos
        logger.info("Position opened: %s %s @ %.2f x%d", journal_id, code, entry_price, shares)
        return journal_id

    async def close_position(
        self, journal_id: str, exit_price: float, exit_reason: str = ""
    ) -> None:
        pos = self._positions.pop(journal_id, None)
        if not pos:
            logger.warning("Position not found: %s", journal_id)
            return

        pos.exit_price = exit_price
        pos.exit_date = date.today()
        pos.exit_reason = exit_reason
        pos.is_open = False
        self._closed.append(pos)

        pnl = (exit_price - pos.entry_price) * pos.shares
        logger.info("Position closed: %s %s pnl=%.2f reason=%s",
                     journal_id, pos.code, pnl, exit_reason)

    async def update_unrealized_pnl(
        self, quotes: dict[str, float]
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for pos in self._positions.values():
            current = quotes.get(pos.code)
            if current is None:
                continue

            pnl = (current - pos.entry_price) * pos.shares
            pnl_pct = (current - pos.entry_price) / pos.entry_price * 100
            risk_per_share = pos.entry_price - pos.stop_loss
            r_multiple = (current - pos.entry_price) / risk_per_share if risk_per_share > 0 else 0

            results.append({
                "journal_id": pos.journal_id,
                "code": pos.code,
                "entry_price": pos.entry_price,
                "current_price": current,
                "shares": pos.shares,
                "unrealized_pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "r_multiple": round(r_multiple, 2),
                "stop_loss": pos.stop_loss,
                "target_price": pos.target_price,
            })

        return results

    async def calculate_position_size(
        self,
        code: str,
        market: MarketType,
        entry_price: float,
        stop_loss: float,
        account_equity: float,
        risk_pct: float = 0.02,
    ) -> dict[str, Any]:
        """ATR 動態倉位計算。"""
        risk_amount = account_equity * risk_pct
        risk_per_share = abs(entry_price - stop_loss)

        if risk_per_share <= 0:
            return {"shares": 0, "risk_amount": 0, "position_value": 0, "error": "Invalid stop loss"}

        # 台股以張(1000股)為單位
        raw_shares = risk_amount / risk_per_share
        if market == MarketType.TW:
            lots = max(1, int(raw_shares / 1000))
            shares = lots * 1000
        else:
            shares = max(1, int(raw_shares))

        position_value = shares * entry_price
        actual_risk = shares * risk_per_share

        return {
            "shares": shares,
            "lots": shares // 1000 if market == MarketType.TW else shares,
            "risk_amount": round(actual_risk, 2),
            "position_value": round(position_value, 2),
            "risk_pct_actual": round(actual_risk / account_equity * 100, 2),
            "entry_price": entry_price,
            "stop_loss": stop_loss,
        }

    async def get_performance_stats(self) -> dict[str, float]:
        if not self._closed:
            return {"win_rate": 0, "avg_r": 0, "expectancy": 0, "total_trades": 0}

        pnls = []
        r_multiples = []
        for pos in self._closed:
            if pos.exit_price is None:
                continue
            pnl = (pos.exit_price - pos.entry_price) * pos.shares
            pnls.append(pnl)
            risk = pos.entry_price - pos.stop_loss
            r = (pos.exit_price - pos.entry_price) / risk if risk > 0 else 0
            r_multiples.append(r)

        if not pnls:
            return {"win_rate": 0, "avg_r": 0, "expectancy": 0, "total_trades": 0}

        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls) * 100
        avg_r = sum(r_multiples) / len(r_multiples)
        expectancy = sum(pnls) / len(pnls)

        return {
            "win_rate": round(win_rate, 2),
            "avg_r": round(avg_r, 2),
            "expectancy": round(expectancy, 2),
            "total_trades": len(pnls),
            "total_pnl": round(sum(pnls), 2),
        }

    async def get_open_positions(
        self, market: MarketType | None = None
    ) -> list[dict[str, Any]]:
        results = []
        for pos in self._positions.values():
            if market and pos.market != market:
                continue
            results.append({
                "journal_id": pos.journal_id,
                "code": pos.code,
                "market": pos.market.value,
                "entry_price": pos.entry_price,
                "shares": pos.shares,
                "stop_loss": pos.stop_loss,
                "target_price": pos.target_price,
                "entry_date": pos.entry_date.isoformat(),
                "entry_reason": pos.entry_reason,
            })
        return results
