"""美股常用股票池與產業分類。"""
from __future__ import annotations

# 美股 Top 50（依市值排序）
US_TOP_STOCKS: list[tuple[str, str, str]] = [
    # (ticker, 名稱, 產業)
    ("AAPL", "Apple", "科技"),
    ("MSFT", "Microsoft", "科技"),
    ("GOOGL", "Alphabet", "科技"),
    ("AMZN", "Amazon", "電商/雲端"),
    ("NVDA", "NVIDIA", "半導體"),
    ("META", "Meta", "社群/AI"),
    ("TSLA", "Tesla", "電動車"),
    ("BRK-B", "Berkshire", "金融"),
    ("TSM", "台積電ADR", "半導體"),
    ("AVGO", "Broadcom", "半導體"),
    ("JPM", "JPMorgan", "金融"),
    ("V", "Visa", "金融科技"),
    ("MA", "Mastercard", "金融科技"),
    ("UNH", "UnitedHealth", "醫療"),
    ("JNJ", "J&J", "醫療"),
    ("XOM", "Exxon", "能源"),
    ("PG", "P&G", "消費"),
    ("HD", "Home Depot", "零售"),
    ("COST", "Costco", "零售"),
    ("ABBV", "AbbVie", "生技"),
    ("CRM", "Salesforce", "SaaS"),
    ("AMD", "AMD", "半導體"),
    ("INTC", "Intel", "半導體"),
    ("QCOM", "Qualcomm", "半導體"),
    ("NFLX", "Netflix", "串流"),
    ("DIS", "Disney", "娛樂"),
    ("PEP", "PepsiCo", "消費"),
    ("KO", "Coca-Cola", "消費"),
    ("MRK", "Merck", "醫療"),
    ("LLY", "Eli Lilly", "生技"),
    # 熱門成長股
    ("PLTR", "Palantir", "AI/數據"),
    ("SNOW", "Snowflake", "雲端"),
    ("COIN", "Coinbase", "加密"),
    ("SQ", "Block", "金融科技"),
    ("SHOP", "Shopify", "電商"),
    # ETF
    ("SPY", "S&P 500 ETF", "ETF"),
    ("QQQ", "Nasdaq 100 ETF", "ETF"),
    ("SOXX", "半導體 ETF", "ETF"),
    ("ARKK", "ARK Innovation", "ETF"),
    ("VTI", "全美市場 ETF", "ETF"),
]

# 美股指數
US_INDICES: list[tuple[str, str]] = [
    ("^DJI", "道瓊"),
    ("^GSPC", "S&P 500"),
    ("^IXIC", "NASDAQ"),
    ("^SOX", "費城半導體"),
    ("^VIX", "VIX 恐慌指數"),
    ("^RUT", "Russell 2000"),
]

# 美股產業分類
US_SECTORS: list[str] = [
    "科技", "半導體", "金融", "金融科技", "醫療", "生技",
    "能源", "消費", "零售", "電商/雲端", "SaaS", "串流",
    "娛樂", "電動車", "社群/AI", "AI/數據", "雲端", "電商",
    "加密", "ETF",
]
