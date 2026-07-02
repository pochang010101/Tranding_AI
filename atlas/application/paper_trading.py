"""紙上交易 — 模擬下單、成交、停損停利、P&L 追蹤。

提供與真實交易相同的 API，但不實際下單。
用於策略驗證、參數調優、信心建立。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from atlas.enums import MarketType

if TYPE_CHECKING:
    from atlas.domain.portfolio import PortfolioManager
    from atlas.infrastructure.quote_adapter import QuoteAdapter

logger = logging.getLogger(__name__)


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class PaperOrder:
    order_id: str
    code: str
    market: MarketType
    side: OrderSide
    shares: int
    limit_price: float | None
    stop_loss: float | None
    take_profit: float | None
    status: OrderStatus = OrderStatus.PENDING
    fill_price: float | None = None
    fill_time: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    reason: str = ""


class PaperTradingEngine:
    """紙上交易引擎。

    功能：
    - 模擬市價/限價單
    - 自動停損/停利觸發
    - 即時未實現損益（透過 QuoteAdapter）
    - 交易日誌與績效統計
    - 與 PortfolioManager 整合
    """

    def __init__(
        self,
        quote_adapter: QuoteAdapter | None = None,
        portfolio: PortfolioManager | None = None,
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.001425,
        tax_rate: float = 0.003,
    ) -> None:
        self._quotes = quote_adapter
        self._portfolio = portfolio
        self._capital = initial_capital
        self._available_capital = initial_capital
        self._commission_rate = commission_rate
        self._tax_rate = tax_rate
        self._orders: dict[str, PaperOrder] = {}
        self._filled_orders: list[PaperOrder] = []
        self._trade_log: list[dict[str, Any]] = []
        self._started = False
        self._start_date: date | None = None

    async def start(self, initial_capital: float | None = None) -> dict[str, Any]:
        """啟動紙上交易。"""
        if initial_capital:
            self._capital = initial_capital
            self._available_capital = initial_capital
        self._started = True
        self._start_date = date.today()
        logger.info("Paper trading started with capital=%.0f", self._capital)
        return {
            "status": "started",
            "capital": self._capital,
            "start_date": self._start_date.isoformat(),
        }

    async def stop(self) -> dict[str, Any]:
        """停止紙上交易，回傳總結。"""
        self._started = False
        summary = await self.get_summary()
        logger.info("Paper trading stopped. PnL=%.2f", summary.get("total_pnl", 0))
        return summary

    async def place_order(
        self,
        code: str,
        market: MarketType,
        side: OrderSide,
        shares: int,
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        reason: str = "",
    ) -> PaperOrder:
        """下單（市價或限價）。"""
        if not self._started:
            raise RuntimeError("Paper trading not started")

        order = PaperOrder(
            order_id=str(uuid.uuid4())[:8],
            code=code,
            market=market,
            side=side,
            shares=shares,
            limit_price=limit_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
        )
        self._orders[order.order_id] = order
        logger.info(
            "Order placed: %s %s %s x%d @ %s",
            order.order_id, side.value, code, shares,
            f"limit={limit_price}" if limit_price else "market",
        )

        # 市價單立即嘗試成交
        if limit_price is None and self._quotes:
            await self._try_fill_market(order)

        return order

    async def cancel_order(self, order_id: str) -> bool:
        """取消未成交訂單。"""
        order = self._orders.get(order_id)
        if not order or order.status != OrderStatus.PENDING:
            return False
        order.status = OrderStatus.CANCELLED
        logger.info("Order cancelled: %s", order_id)
        return True

    async def check_and_fill_pending(self) -> list[PaperOrder]:
        """檢查限價單是否可成交 + 停損停利觸發。"""
        if not self._quotes:
            return []

        filled: list[PaperOrder] = []

        for order in list(self._orders.values()):
            if order.status != OrderStatus.PENDING:
                continue

            try:
                quote = await self._quotes.get_quote(order.code, order.market)
                current_price = float(quote.price)
            except Exception:
                continue

            # 限價單成交判斷
            if order.limit_price is not None:
                if order.side == OrderSide.BUY and current_price <= order.limit_price:
                    await self._fill_order(order, current_price)
                    filled.append(order)
                elif order.side == OrderSide.SELL and current_price >= order.limit_price:
                    await self._fill_order(order, current_price)
                    filled.append(order)

        # 檢查已持有部位的停損停利
        filled.extend(await self._check_stop_take())

        return filled

    async def get_positions(self) -> list[dict[str, Any]]:
        """取得目前持倉。"""
        if self._portfolio:
            return await self._portfolio.get_open_positions()
        return []

    async def get_summary(self) -> dict[str, Any]:
        """取得紙上交易總結。"""
        stats: dict[str, float] = {}
        if self._portfolio:
            stats = await self._portfolio.get_performance_stats()

        # 計算已實現損益
        realized_pnl = sum(t.get("pnl", 0) for t in self._trade_log)

        return {
            "status": "stopped" if not self._started else "running",
            "start_date": self._start_date.isoformat() if self._start_date else None,
            "initial_capital": self._capital,
            "available_capital": round(self._available_capital, 2),
            "total_orders": len(self._orders) + len(self._filled_orders),
            "filled_orders": len(self._filled_orders),
            "total_pnl": round(realized_pnl, 2),
            "return_pct": round(realized_pnl / self._capital * 100, 2) if self._capital else 0,
            "performance": stats,
            "trade_count": len(self._trade_log),
        }

    async def get_trade_log(self) -> list[dict[str, Any]]:
        """取得完整交易日誌。"""
        return list(self._trade_log)

    # ── 內部方法 ────────────────────────────────

    async def _try_fill_market(self, order: PaperOrder) -> None:
        """嘗試以市價成交。"""
        try:
            quote = await self._quotes.get_quote(order.code, order.market)
            await self._fill_order(order, float(quote.price))
        except Exception as exc:
            logger.warning("Market fill failed for %s: %s", order.order_id, exc)
            order.status = OrderStatus.REJECTED
            order.reason = str(exc)

    async def _fill_order(self, order: PaperOrder, price: float) -> None:
        """成交訂單，更新資金與持倉。"""
        cost = price * order.shares
        commission = cost * self._commission_rate
        tax = cost * self._tax_rate if order.side == OrderSide.SELL else 0

        if order.side == OrderSide.BUY:
            total_cost = cost + commission
            if total_cost > self._available_capital:
                order.status = OrderStatus.REJECTED
                order.reason = "Insufficient capital"
                logger.warning("Order rejected: insufficient capital for %s", order.order_id)
                return
            self._available_capital -= total_cost

            # 加入持倉
            if self._portfolio:
                await self._portfolio.add_position(
                    code=order.code,
                    market=order.market,
                    entry_price=price,
                    shares=order.shares,
                    stop_loss=order.stop_loss or price * 0.95,
                    target_price=order.take_profit,
                    entry_reason=order.reason,
                )
        else:
            net_proceeds = cost - commission - tax
            self._available_capital += net_proceeds

        order.status = OrderStatus.FILLED
        order.fill_price = price
        order.fill_time = datetime.utcnow()

        self._filled_orders.append(order)
        self._orders.pop(order.order_id, None)

        pnl = 0.0
        if order.side == OrderSide.SELL:
            pnl = net_proceeds - cost  # simplified; actual PnL tracked by portfolio

        trade_record = {
            "order_id": order.order_id,
            "code": order.code,
            "side": order.side.value,
            "shares": order.shares,
            "price": price,
            "commission": round(commission, 2),
            "tax": round(tax, 2),
            "pnl": round(pnl, 2),
            "timestamp": order.fill_time.isoformat(),
        }
        self._trade_log.append(trade_record)

        logger.info(
            "Order filled: %s %s %s x%d @ %.2f (commission=%.0f, tax=%.0f)",
            order.order_id, order.side.value, order.code,
            order.shares, price, commission, tax,
        )

    async def _check_stop_take(self) -> list[PaperOrder]:
        """檢查已持倉的停損/停利觸發。"""
        if not self._portfolio or not self._quotes:
            return []

        triggered: list[PaperOrder] = []
        positions = await self._portfolio.get_open_positions()

        for pos in positions:
            code = pos["code"]
            try:
                quote = await self._quotes.get_quote(code, MarketType(pos["market"]))
                current = float(quote.price)
            except Exception:
                continue

            stop_loss = pos.get("stop_loss")
            target = pos.get("target_price")

            reason = ""
            if stop_loss and current <= stop_loss:
                reason = "stop_loss"
            elif target and current >= target:
                reason = "take_profit"

            if reason:
                sell_order = await self.place_order(
                    code=code,
                    market=MarketType(pos["market"]),
                    side=OrderSide.SELL,
                    shares=pos["shares"],
                    reason=reason,
                )
                if sell_order.status == OrderStatus.FILLED:
                    triggered.append(sell_order)

                    # 平倉
                    await self._portfolio.close_position(
                        pos["journal_id"],
                        exit_price=current,
                        exit_reason=reason,
                    )

        return triggered
