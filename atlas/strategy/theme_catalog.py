"""題材概念股分類 — 台股主要題材與成分股對照表 + 熱度偵測。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)

# ── 題材定義：{題材名稱: [成分股代碼]} ──
# 一支股票可屬於多個題材
THEME_MAP: dict[str, list[str]] = {
    "AI": [
        "2330", "2454", "3443", "2382", "2308", "3231", "6547",
        "3661", "2379", "6669", "3035", "2376", "5274", "6770",
        "3529", "2449", "6409", "3536", "2301",
    ],
    "半導體": [
        "2330", "2303", "2454", "3711", "2379", "6770", "3443",
        "5274", "3034", "2408", "6488", "5269", "3529", "2344",
        "6239", "8150", "3661", "2449", "6547",
    ],
    "CoWoS先進封裝": [
        "3711", "2330", "3443", "6547", "3034", "2449", "6239",
    ],
    "HBM記憶體": [
        "2344", "3443", "6770", "4967", "5765",
    ],
    "伺服器": [
        "2382", "2356", "3231", "2353", "6669", "3035", "2376",
        "3036", "3044", "2395", "2301", "3017",
    ],
    "散熱": [
        "3017", "6230", "3653", "2059", "6569",
    ],
    "PCB": [
        "2383", "3037", "8046", "2368", "3189", "6269", "2313",
    ],
    "ASIC": [
        "2379", "3661", "5274", "6547", "3536",
    ],
    "蘋果供應鏈": [
        "2317", "2354", "3008", "2474", "3711", "2382", "6488",
        "3443", "2327", "4938", "6285", "2308",
    ],
    "電動車": [
        "2207", "2201", "2308", "3443", "3035", "6285", "2327",
        "4938", "1590", "3702", "6186",
    ],
    "綠能儲能": [
        "6244", "3576", "6443", "3514", "1513", "1519", "6691",
        "3552", "6547",
    ],
    "軍工國防": [
        "2208", "2634", "2014", "1513", "4551", "3535",
        "6462", "2601",
    ],
    "生技": [
        "4743", "6446", "4174", "6472", "1707", "1760", "4137",
        "6589", "4746", "1734",
    ],
    "金融": [
        "2881", "2882", "2891", "2886", "2884", "2892", "5880",
        "2880", "2885", "2887", "2888", "2883",
    ],
    "高股息": [
        "2412", "1301", "2882", "2886", "5880", "2892", "2880",
        "9910", "1216", "2885", "3045", "4904",
    ],
    "航運": [
        "2603", "2609", "2615", "2606", "5765",
    ],
    "機器人": [
        "2317", "2382", "4510", "3443", "6547", "2308", "2049",
    ],
    "資安": [
        "6214", "4953", "6690", "2439",
    ],
    "5G通訊": [
        "2412", "3045", "4904", "3034", "2313", "3037", "2474",
    ],
}

# 反向索引：code → [題材列表]
_CODE_TO_THEMES: dict[str, list[str]] = {}
for _theme, _codes in THEME_MAP.items():
    for _code in _codes:
        _CODE_TO_THEMES.setdefault(_code, []).append(_theme)


def get_themes_for_code(code: str) -> list[str]:
    """取得股票所屬題材列表。"""
    return _CODE_TO_THEMES.get(code, [])


@dataclass
class ThemeHeat:
    """題材熱度。"""
    name: str
    stock_count: int = 0
    up_count: int = 0
    avg_change_pct: float = 0.0
    top_stocks: list[str] = field(default_factory=list)
    heat_score: float = 0.0  # 0~100


def detect_hot_themes(daily_df: pd.DataFrame, top_n: int = 10) -> list[ThemeHeat]:
    """偵測當日熱門題材。

    Args:
        daily_df: 全市場日行情 DataFrame（需有 code, change_pct 欄位）
        top_n: 回傳前 N 個熱門題材

    Returns:
        按熱度排序的題材列表
    """
    if daily_df.empty or "code" not in daily_df.columns:
        return []

    code_change = dict(zip(daily_df["code"], daily_df["change_pct"], strict=False))
    code_name = dict(zip(daily_df["code"], daily_df.get("name", daily_df["code"]), strict=False))

    results = []
    for theme_name, members in THEME_MAP.items():
        changes = []
        up = 0
        top_list = []

        for code in members:
            if code in code_change:
                chg = code_change[code]
                changes.append(chg)
                if chg > 0:
                    up += 1
                top_list.append((code, code_name.get(code, code), chg))

        if not changes:
            continue

        avg_chg = sum(changes) / len(changes)
        up_ratio = up / len(changes) if changes else 0

        # 熱度分數：平均漲幅權重60% + 上漲比例權重40%
        # 正規化到 0~100
        heat = max(0, min(100, avg_chg * 15 + up_ratio * 40 + 30))

        # Top 漲幅成分股
        top_list.sort(key=lambda x: x[2], reverse=True)
        top_display = [f"{c}({n} {v:+.1f}%)" for c, n, v in top_list[:3]]

        results.append(ThemeHeat(
            name=theme_name,
            stock_count=len(changes),
            up_count=up,
            avg_change_pct=round(avg_chg, 2),
            top_stocks=top_display,
            heat_score=round(heat, 1),
        ))

    results.sort(key=lambda x: x.heat_score, reverse=True)
    return results[:top_n]
