"""Atlas 全域常數 — 集中定義跨模組共用的常數與工具函式。"""

from __future__ import annotations

from zoneinfo import ZoneInfo

TW_TZ = ZoneInfo("Asia/Taipei")

# 已知上櫃(OTC)股票代碼集合；TSE 查無資料時也可動態發現
OTC_CODES: frozenset[str] = frozenset({
    "5269", "6488", "6669", "3293", "8069", "6147", "3529", "6770", "8454", "5871",
})


def is_otc(code: str) -> bool:
    """判斷是否為上櫃股票（OTC）。"""
    return code in OTC_CODES
