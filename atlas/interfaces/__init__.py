"""atlas/interfaces — 全系統 ABC / Protocol 介面定義。

按架構分層匯出所有介面，供 DI 容器與測試 mock 使用。
"""

from __future__ import annotations

# L4 Application
from atlas.interfaces.application import (
    IBacktestEngine,
    IConclusionEngine,
    INotificationHub,
    IRealtimeRadar,
    IRiskSimulator,
    ISchedulerService,
    IScreenerEngine,
    IWorkflowEngine,
)

# L2 Domain
from atlas.interfaces.domain import (
    IBreadthService,
    IInternationalMarket,
    IMarketRegimeService,
    IPortfolioManager,
    ISentimentService,
    IUniverseManager,
)

# L1 Infrastructure
from atlas.interfaces.infrastructure import (
    ICacheService,
    IDataManager,
    INotificationAdapter,
    IQuoteAdapter,
    IRepository,
)

# L3 Strategy
from atlas.interfaces.strategy import (
    IGapPredictor,
    IIndicatorLibrary,
    IIPOModule,
    IMLEngine,
    IMonteCarloSimulator,
    IScoringEngine,
    ISMCModule,
    IStrategy,
)

__all__ = [
    # L1 Infrastructure
    "ICacheService",
    "IDataManager",
    "INotificationAdapter",
    "IQuoteAdapter",
    "IRepository",
    # L2 Domain
    "IBreadthService",
    "IInternationalMarket",
    "IMarketRegimeService",
    "IPortfolioManager",
    "ISentimentService",
    "IUniverseManager",
    # L3 Strategy
    "IGapPredictor",
    "IIndicatorLibrary",
    "IIPOModule",
    "IMLEngine",
    "IMonteCarloSimulator",
    "IScoringEngine",
    "ISMCModule",
    "IStrategy",
    # L4 Application
    "IBacktestEngine",
    "IConclusionEngine",
    "INotificationHub",
    "IRealtimeRadar",
    "IRiskSimulator",
    "ISchedulerService",
    "IScreenerEngine",
    "IWorkflowEngine",
]
