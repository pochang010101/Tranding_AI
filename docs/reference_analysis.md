# Atlas v5.0 — 參考來源完整分析報告

> **文件編號**：DOC-REF-001
> **版本**：v1.0
> **分析日期**：2026-07-11
> **分析範圍**：`參考來源/` 目錄 27 個檔案 vs Atlas v5.0 現有專案
> **分析方法**：5 組平行 Explore Agent 全文閱讀 → 交叉比對 → 差異歸類 → 路線圖建議

---

## 目錄

1. [執行摘要](#一執行摘要)
2. [參考文件清冊與分類](#二參考文件清冊與分類)
3. [各文件深度摘要](#三各文件深度摘要)
4. [Atlas v5.0 現有能力盤點](#四atlas-v50-現有能力盤點)
5. [差異分析矩陣](#五差異分析矩陣)
6. [量化差距統計](#六量化差距統計)
7. [跨系統架構比較](#七跨系統架構比較)
8. [風險與根因分析](#八風險與根因分析)
9. [優化與擴充建議](#九優化與擴充建議)
10. [實作路線圖](#十實作路線圖)
11. [結論](#十一結論)

---

## 一、執行摘要

本報告針對 Atlas Trading System v5.0 的 27 份參考來源文件進行全面分析，涵蓋四套既有投資系統（台股 AI 看盤、選股系統、Atlas Signal Radar、Signal Radar）的設計規格、技術架構、操作手冊，以及獨立策略框架（Qullamaggie、波浪葛蘭碧、朱家泓飆股）。

### 核心發現

| 維度 | 結論 |
|------|------|
| **架構成熟度** | Atlas v5.0 的工程架構（5 層分離、PG+Redis、Docker、CI/CD、248 tests）**顯著優於**所有參考系統 |
| **策略深度** | 參考來源涵蓋 15 套流派/策略，Atlas 僅實作 7 套，**覆蓋率 47%** |
| **量化自進化** | 因子探勘管線（IC/ICIR）、天天回測篩選 Atlas **完全缺失**，是最大戰略缺口 |
| **決策一致性** | 17 號文件揭露的 12 項矛盾有 5 項**直接映射**到 Atlas 現有程式碼 |
| **盤前情報** | 開盤缺口預測模組 Atlas **完全缺失**，盤前工作流價值未完全釋放 |
| **即時下單** | Atlas 僅有 Paper Trading，**缺少真實券商串接**（群益 SKCOM / Shioaji） |

### 三大最高價值行動

1. **修復選股矛盾**（P0）— 確保現有功能正確性，消滅雙軌結論
2. **建立因子探勘管線**（P0）— 從「人工定規則」進化到「數據驅動」
3. **開盤缺口預測**（P0）— 填補盤前決策最後一塊拼圖

---

## 二、參考文件清冊與分類

### 2.1 設計規格類（8 份）

| 編號 | 檔案名稱 | 頁數 | 核心主題 | 對應 Atlas 層 |
|------|---------|------|---------|--------------|
| 00 | 系統架構圖與分析設計規格書 | ~180行 | Signal Radar 五層架構、15 流派、9 偵測器 | Strategy / Application |
| 01 | 選股系統_設計規格 | ~120行 | XQ XS 三層選股（技術+籌碼+財務） | Strategy |
| 02 | 雷達偵測_設計規格 | ~130行 | XQ 盤中三類異常偵測 | Application |
| 03 | 自訂指標_設計規格 | ~110行 | 跨頻率 MA / 籌碼強度 / 趨勢狀態指標 | Strategy |
| 04 | 自動交易_設計規格 | ~140行 | XQ 日內當沖策略（金叉 / 爆量突破） | Application |
| 05 | 推送系統_設計規格 | ~100行 | XQ Log → Telegram 推播管線 | Infrastructure |
| 06 | 因子探勘_設計規格 | ~150行 | IC/ICIR 量化因子評估管線 | Strategy (NEW) |
| 14 | UI設計系統_TradingView風格 | ~90行 | 深色主題色彩 Token / 卡片規範 | Presentation |

### 2.2 策略流派類（4 份）

| 編號 | 檔案名稱 | 核心主題 | 策略數量 |
|------|---------|---------|---------|
| 07 | 波浪葛蘭碧蕭明道_整合系統規格 | 三套技術分析整合：波浪→葛蘭碧→量價供需 | 3 套 × 3 層 |
| 08 | 朱家泓飆股上校_系統規格 | 均線戰法 + N 字底型態偵測 | 2 套核心 |
| 10 | 訊號指標說明 | 五層訊號 + 四擴充模組 + 多流派共識 | 5 層 + 4 模組 |
| — | qullamaggie_agent_framework | Qullamaggie 突破策略 AI Agent 框架 | 1 套 + 4 Regime |

### 2.3 系統整合與部署類（4 份）

| 編號 | 檔案名稱 | 核心主題 |
|------|---------|---------|
| 16 | 隔夜國際行情整合與開盤缺口預測規格 | ADR / 費半 / ES 夜盤 → 缺口預測 |
| 17 | 選股結果欄位矛盾檢討與處理方案 | 12 項矛盾分析 + 四批修復方案 |
| 20 | 本地雲端同步_即時交易_佈署規格 | 群益下單 + SQLite→TiDB 同步 + Render |
| — | API.md | 20+ REST 端點規範 |

### 2.4 既有系統文件類（9 份）

| 檔案名稱 | 對應系統 | 技術棧 |
|---------|---------|--------|
| Atlas_技術架構白皮書.html | Atlas Signal Radar (Mindao) | Streamlit + GitHub Actions + 群益 |
| Atlas_使用者操作手冊.html | Atlas Signal Radar | 9 分頁操作 SOP |
| Atlas_系統介紹.html | Atlas Signal Radar | 22 日K策略 + 6 盤中訊號 |
| system_introduction.html | Signal Radar 多流派系統 | Streamlit + Discord + LINE |
| system_intro.html | Atlas Signal Radar v2.0 | 三大流派融合 |
| introduction.html | 台股 AI 看盤 (MasterTalks) | Gradio + ML Pipeline |
| Stock_Strategy_system_intro.html | O'Neil 選股紀律系統 | Streamlit + 16 分制評分 |
| TECHNICAL_forex.md | 外匯監控系統 | Flask + SQLite |
| TECHNICAL_webapp.md | 台股主力監控控制台 | Flask + SQLite |

### 2.5 其他（2 份）

| 檔案名稱 | 說明 |
|---------|------|
| Qullamaggie 突破策略…全指南.pdf | 突破策略教科書（PDF） |
| 短線交易系統_README.md | 文件遷移公告（已整併至 README.md） |

---

## 三、各文件深度摘要

### 3.1 「00_系統架構圖與分析設計規格書」

Signal Radar 訊號系統的完整五層架構定義文件。

**五層訊號架構**：
- **L1 年線層**（MA240）：牛熊市定位，±1 分
- **L2 季線層**（MA60）：中期趨勢，±1 分
- **L3 葛蘭碧層**：八大法則，BUY +1~+3 / SELL -1~-3
- **L4 量價層**：蕭明道量價供需，±3 分
- **L5 短線層**：活動靶系統，+1 分

**關鍵功能**：
- 股票池建構與多維篩選（產業、主題、集團、量能過濾）
- 15 個流派系統統一評等（強買/買進/觀察/中性/賣出/強賣）
- 市場環境三層判斷（趨勢 + 情緒五因子 + 寬度指標）
- ATR 倉位計算與情緒感知停損
- 4 個回測模式（單次 / Compare / Screen / 風險層）
- 即時雷達 9 個偵測器
- Dashboard 4 個 Tab + Discord 推播

**Atlas 對照**：Atlas scoring_engine 有四主軸+三面向，但缺少完整的五層訊號架構和 15 流派統一評等。

---

### 3.2 「01_選股系統_設計規格」

XQ XS 腳本實作的多因子三層選股規格。

**三層篩選**：
1. **技術面**（3 條）：股價位置、近期高點突破、收紅 K
2. **籌碼面**（3 條）：外資連續買超、累計買超、大戶持股上升
3. **財務面**（2 條）：營收年增率、EPS 正值

**關鍵設計**：
- 14 個變數 + 9 個條件宣告表
- Rank 排行前 30 名（外資買賣超降冪排序）
- 5 個高風險點識別（未來資料 / 函數索引 / Rank 語意 / 週頻語意 / 邊界定義）

**Atlas 對照**：Atlas 不使用 XQ，改用 Python 原生實作（正確方向）。scoring_engine 的三面向（技術/基本/籌碼）與此對應，但條件粒度較粗。

---

### 3.3 「02_雷達偵測_設計規格」

盤中即時雷達警示系統，三個獨立 XS 腳本。

**三類偵測**：
1. **產業急拉**：5 分鐘漲幅 > 1% AND 外盤 > 內盤
2. **大單異常**：買進大單 > 均量 × 3 AND 外盤 > 內盤 × 1.5
3. **爆量啟動**：即時量 > 昨日量 × 50% AND 創近 20 日新高 AND 非處置股

**Atlas 對照**：realtime_radar 已有 11 偵測器（100% 覆蓋），含 SMC 的流動性掃單和 OB 回測。

---

### 3.4 「03_自訂指標_設計規格」

三個自訂技術指標的設計。

**指標清單**：
1. 分鐘圖疊加日線 MA 系統（MA5/MA20/MA60 + 金叉偵測）
2. 籌碼強度指標（外資/投信 3/5/10 日累計）
3. 趨勢狀態量化（多頭/盤整/空頭判斷）

**Atlas 對照**：indicator_lib 已有 MA/RSI/MACD/BB/ATR/KD/OBV/VP 共 12 種，缺少跨頻率疊加和籌碼強度指標。

---

### 3.5 「04_自動交易_設計規格」

兩個日內當沖策略的完整規格。

**策略一**：日線 MA 金叉當沖（5 分鐘主圖、3% 停損 + 移動停損 2% + 5% 停利）
**策略二**：爆量突破策略（1 分鐘主圖、1.5% 停損、強制收盤平倉）

**關鍵設計**：
- SetPosition(0/1) 狀態機
- 出場優先級：強制平倉 > 固定停損 > 移動停損 > 固定停利 > 進場訊號
- 移動停損時序設計（進場初始化 → 最高點追蹤 → 啟動門檻 → 追蹤線更新）
- CSV Log 格式 + 過度擬合排查清單

**Atlas 對照**：paper_trading 可模擬，backtest_engine 有 walk-forward，但缺真實下單和移動停損時序。

---

### 3.6 「05_推送系統_設計規格」

XQ Log 檔 → Telegram 推播的輕量推送系統。

**關鍵設計**：
- Seek-to-end 檔案監控 + 多檔並行
- CSV 格式解析 + 類型識別（警示 / 交易 / 選股）
- MD5 Hash LRU 快取去重
- Bot API 直接呼叫 + 失敗自動重試 3 次
- PyInstaller 打包成 Windows .exe

**Atlas 對照**：notification_hub 已有 Discord/LINE/Telegram/Email 四通道 Fallback，架構更完善。

---

### 3.7 「06_因子探勘_設計規格」 ⭐ 重要缺口

量化因子自動評估管線的完整規格。

**核心流程**：
- XQ OutputField → Python 資料清洗 → IC 計算 → 多因子組合 → HTML 報告
- **IC**（Spearman 等級相關係數）：衡量因子預測力
- **ICIR**（IC / std(IC)）：衡量因子穩定性
- 有效性門檻：IC 均值 > 0.03、ICIR > 0.3、p < 0.05

**因子生命週期管理**：
```
觀察中 → 候選 → 核心 → 衰退 → 淘汰
```

**過度挖掘防控**：
- Benjamini-Hochberg 多重比較校正
- 樣本外驗證 + 假說先行原則
- 最低持續期門控

**三組因子設計**：
- 籌碼組（外資連買天數 / 投信連買天數 / 大戶增減 / 融資變化）
- 技術組（均線排列分 / RSI14 / 葛蘭碧訊號 / 近月漲幅 / 量能比 / 20日波動率）
- 財務組（營收YoY / EPS成長 / 毛利率 / ROE）

**更新排程**：日 / 週 / 月 / 季度觸發 + 滾動評估

**Atlas 對照**：**完全缺失**。Atlas 目前的選股因子全靠人工定義規則，無法自動發現和淘汰失效因子。這是最大的量化能力缺口。

---

### 3.8 「07_波浪葛蘭碧蕭明道_整合系統規格」

三套技術分析方法的整合框架：「戰略→戰術→執行」。

**三層 MA 架構**：
- L1 年線（MA240）：杜金龍波浪理論，牛熊定位
- L2 季線（MA60）：中期趨勢方向
- L3 月線（MA20）：短期作戰基準

**葛蘭碧八大法則**：
- BUY1-4：遠離回升 / 突破 / 回測不破 / 超跌反彈
- SELL5-8：對稱的四種賣出訊號
- 每個訊號附星級評分（★★★ 最強）

**訊號強度 9 宮格矩陣**（L1 × L2+L3 組合）：
- 回答「現在是否該出手」
- 強買 / 弱買 / 觀望 / 弱賣 / 強賣

**蕭明道量價評分**：
- 量增價漲 / 量縮價漲 / 量縮價跌 / 量增價跌
- 凹洞量 / 三盤突破 / 均量帶動

**活動靶系統**：MA5 多頭啟動 → 良性整理 → 警示出場

**Atlas 對照**：scoring_engine 有基礎訊號計算，但缺完整的八法星級矩陣、9 宮格、活動靶系統。

---

### 3.9 「08_朱家泓飆股上校_系統規格」

均線戰法 + N 字底型態的完整框架。

**6 字訣趨勢判斷**：頭頭高 / 底底高（多頭）vs 頭頭低 / 底底低（空頭）

**N 字底四要素**：
1. 底底高（近 10 根最低 > 前 10 根最低）
2. 頭頭高（近 10 根最高 > 前 10 根最高）
3. 底部築底 → 反彈 → 拉回 → 再漲突破
4. 四要素結構完整度評分

**買進條件**：MA20 上彎（必要）+ Close > MA20（必要）+ 底底高 + 頭頭高（必要）+ 均線排列 / 量價加分

**Atlas 對照**：scoring_engine 有 jiahong_bonus 概念，但缺完整的 N 字底偵測和均線排列完美度評分。

---

### 3.10 「10_訊號指標說明」

五大核心訊號 + 四擴充模組的完整說明。

**五大核心訊號**：
1. **綜合評分**（-6 ~ +8）：五層訊號加權
2. **訊號強度**（★★★強買 ~ ★★★強賣）：L1/L2/L3 方向矩陣
3. **共識判斷**（★★最強 / 同向 / 分歧）：一致性檢查
4. **飆股訊號**（★強買 / N字底 / 均線多頭 / 空）
5. **葛蘭碧八法**（BUY1-4 / SELL5-8）

**四個擴充模組**：
1. **動能共振**（0-3 分）：RSI + 季線 + 近季漲幅
2. **VCP 波動收縮**（0-3 星）：三段振幅遞減
3. **RSI 強弱指數**：Wilder RSI(14) 區間解讀
4. **布林通道**：價格位置 + 通道寬度

**多流派不同步說明**：各層時間維度不同，底部反彈時常分歧，★★ 共識才是高確信度。

**Atlas 對照**：conclusion_engine 有七級結論，但缺少訊號強度（SignalStrength）和共識判斷（ConsensusLevel）兩個維度。

---

### 3.11 「14_UI 設計系統_TradingView 風格」

深色終端風格的 UI 設計系統規範。

**色彩 Token 系統**（8 核心 token）：
| Token | 色碼 | 用途 |
|-------|------|------|
| bg-base | #131722 | 頁面背景 |
| bg-panel | #1E222D | 卡片/面板 |
| text-primary | #D1D4DC | 主文字 |
| text-secondary | #787B86 | 次要文字 |
| bull-red | #F23645 | 台股漲紅 |
| bear-green | #089981 | 台股跌綠 |
| accent-blue | #2962FF | 互動元素 |
| warn-orange | #FF9800 | 警示 |

**卡片設計規範**：
- 買入卡片：左色條標示結論等級（優先進場紅 / 可進場橘 / 小倉試單灰）
- 流派卡片：主流派 2px 藍邊框 + 藍色光暈
- 數字密集區加 `tabular-nums` 對齊

**Atlas 對照**：Streamlit 使用基礎樣式，可直接套用此規範大幅提升視覺品質。

---

### 3.12 「16_隔夜國際行情整合與開盤缺口預測規格」 ⭐ 重要缺口

盤前缺口預測的完整規格。

**三個建設方向**：
1. **排程化擷取**：每日累積至 `intl_history.jsonl`
2. **缺口預測模組**：ADR 漲跌% + 費半% + ES 夜盤% → 加權預測
3. **晨報整合**：讀取 `gap_forecast.json` 產出「📐 開盤缺口預估」段

**預測輸入**：
- 台積電 ADR 隔夜漲跌%
- 費半 ^SOX 漲跌%
- ES=F 夜盤推估%

**輸出**：加權指數預估開盤缺口點數 + 百分比 + 信心度 + 重點股預估

**驗證計畫**：累積 ≥20 交易日後做「預估 vs 實際」相關性檢視

**Atlas 對照**：**完全缺失**。workflow_engine 的 pre_market 有國際行情收集，但無缺口預測功能。

---

### 3.13 「17_選股結果欄位矛盾檢討與處理方案」 ⭐ 直接適用

12 項系統性矛盾的深度分析。

**P0 矛盾（結論與訊號級別）**：
- M1：評分與訊號強度脫鉤（高分可顯弱勢）
- M2：結論欄雙軌制（流派 rank vs legacy 字串，三套邏輯並存）
- M3：結論「空/出場」與飆股「★強買」並存

**P1 矛盾（擴充模組與濾網）**：
- M4：飆股★強買無年線檢查
- M5：動能/VCP/RS/BB 只顯示不進評分
- M6：濾網降級只動結論欄，其他欄位不同步
- M7：共識與結論判斷基準不一致
- M8：反向訊號純加總抵消無衝突標記

**P2 矛盾（排序與資料品質）**：
- M9：勝率與主流派選擇脫節
- M10：排序鍵與結論優先序不同步
- M11：字串包含式判斷脆弱
- M12：資料層降級風險（Mock / None→0）

**根因歸納**：
1. 無單一結論真相源
2. 顯示值與決策值混用
3. 字串即介面（無 Enum）
4. 缺值與中性不分

**Atlas 直接映射**（詳見第八節）。

---

### 3.14 「20_本地雲端同步_即時交易_佈署規格」

本地 Windows + 雲端免費層的整合架構。

**三層架構**：
1. **本地 Windows**：群益 SKCOM → 即時引擎 → LINE Bot → 下單
2. **盤後批次**：SQLite → TiDB Cloud + Backblaze B2
3. **雲端免費層**：GitHub Actions 備援 + Render Dashboard

**通知雙管道**：
- Discord Webhook：晨報 / 日報 / 週報（無上限）
- LINE Bot Messaging API：交易確認 Flex 按鈕（200 則/月）

**群益 Capital API**：
- SKCOM.dll（Windows COM），僅 Windows 執行
- Tick 訂閱 50 檔 / Quote 訂閱 ~4900 檔
- SKOrderLib_SendOrder 下單（需憑證 .pfx + 2FA）

**五重風控**：處置股 / 當日次數 / 單筆金額 / 停損檢查 / 冷卻時間

**天天回測**：
- 雙門檻：勝率 ≥ 55% + 期望值 ≥ 0.3%/trade + 樣本 ≥ 20 筆 + MDD ≤ 15%
- 每日 15:30 全策略回測，自動停用低於門檻的策略

**Atlas 對照**：Atlas 用 PG+Redis+Docker（更強），但缺群益下單、天天回測、雲端免費層備援。

---

### 3.15 「qullamaggie_agent_framework」

Qullamaggie 突破策略的 AI Agent 框架。

**三層架構**：
1. **客觀規則層**（不可覆寫）：200MA 趨勢 + 動能門檻 + 盤整收縮 + RSI ≥ 47
2. **大盤環境動態權重**：Bull / Normal / Recovery / Bear 四種 Regime
3. **催化劑評分**（1-10 分）：敘事熱度 30% + 利多未反映 25% + 社群聲量 20% + 產業趨勢 15% + 時間窗口 10%

**分段獲利**：入場後 3-5 天賣 1/3 → 跌破 10MA 賣 1/3 → 跌破 20MA 清倉

**假突破處理**：突破後 2 日內跌回 = 假突破，立即離場

**Atlas 對照**：Atlas 無此策略，但 Market Regime 動態權重設計值得整合至 market_regime.py。

---

### 3.16 「TECHNICAL_forex」— 外匯監控系統

獨立的 Flask + SQLite 外匯監控平台。

**功能**：五大貨幣對匯率（USD/TWD 優先）+ 套息交易分析 + 財經事件日曆 + 台股匯率連動提示
**技術指標**：SMA(5/20/60) + RSI(14) + 葛蘭碧六種訊號
**三層 Fallback**：Yahoo Finance → open.er-api → 台銀牌告 → Alpha Vantage

**Atlas 對照**：**完全缺失**。可作為 Atlas 的輔助模組，提供匯率風險因子。

---

### 3.17 「TECHNICAL_webapp」— 台股主力監控控制台

Flask + SQLite 多模組整合平台。

**核心引擎**：
- **七維度選股**：法人 20% + 連買 22% + 資金流 20% + 相對強度 8% + 趨勢 17% + 量價 8% + 產業 5%
- **四主力階段**：吸籌 → 洗盤 → 拉升 → 出貨（四維度加權：量能 30% + 價格 30% + 均線 20% + 動能 20%）
- **開盤意圖**：7 種分類（強勢拉升 / 開高走低 / 試探 / 洗後承接 / 賣壓 / 偷吃貨 / 中性）
- **交易價位**：支撐壓力 + 費波那契回撤 + 風險報酬比

**Atlas 對照**：主力階段偵測和開盤意圖判斷完全缺失，交易價位計算部分缺失。

---

### 3.18 「Stock_Strategy_system_intro」— O'Neil 選股系統

Streamlit 16 分制 O'Neil 評分系統。

**16 分制評分**：均線排列 4 分 + 價位關係 3 分 + 量能 4 分 + 收斂與指標 5 分
**三種篩選模式**：嚴格 / 趨勢穩定 / TradingView 回調
**蒙地卡羅風控**：1000 條路徑 × 可調參數（勝率/損益%/風險%）
**R 倍數追蹤**：標準化風險調整報酬 + 期望值計算

**Atlas 對照**：monte_carlo.py 和 portfolio.py（R-multiple）已覆蓋。16 分制評分邏輯可借鏡但 Atlas 的四軸+三面向體系更全面。

---

### 3.19 既有系統 HTML 文件群（6 份）

| 文件 | 關鍵差異點 |
|------|-----------|
| Atlas_技術架構白皮書 | 22 個日K策略六大系列 + importlib 動態載入整合契約層 + 韌性設計（_safe_call 吞例外）|
| Atlas_使用者操作手冊 | 每日操作節奏 SOP + 資料更新時點 + 強制刷新按鈕設計 |
| Atlas_系統介紹 | 費氏數列 MA 骨架(8/21/55/89) + 結論七級三層降級 + 程式碼三層結構(35+18+15支) |
| system_introduction | 20 個分析模組(A~J+SMC+偵測器) + 六套交易策略 + IPO 工具組(折價率+蜜月期追蹤) |
| system_intro | 四大模組融合計分 + CLI 統一指令 + 核心理念(量價為王/均線不騙人) |
| introduction (MasterTalks) | 七層 ML Pipeline + 20+ 特徵工程 + 防未來函數三層檢查 + 台股成本 0.685% |

---

### 3.20 「API.md」— REST API 規範

20+ 端點的完整 RESTful API 設計。

**端點分類**：
- 儀表板摘要 / 選股+背景任務 / 觀察清單 CRUD / 個股判讀卡片
- 訊號記錄 / 盤中監控 / 系統設定 / 台銀匯率 / 國際交叉匯率 / 作戰 Checklist

**Atlas 對照**：Atlas 目前僅有 Streamlit 前端，**無獨立 REST API server**，限制了與外部系統的整合能力。

---

## 四、Atlas v5.0 現有能力盤點

### 4.1 架構層級

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                         │
│  Streamlit 13 頁 (P-01~P-13) + Auth + PWA                   │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                          │
│  screener_engine │ conclusion_engine │ backtest_engine       │
│  realtime_radar  │ paper_trading     │ workflow_engine       │
│  scheduler                                                   │
├─────────────────────────────────────────────────────────────┤
│                    Strategy Layer                             │
│  indicator_lib (12 指標) │ scoring_engine (4軸+3面向)        │
│  smc_module │ ml_engine (RandomForest) │ monte_carlo         │
├─────────────────────────────────────────────────────────────┤
│                     Domain Layer                             │
│  trading_calendar │ market_regime │ sentiment │ portfolio    │
│  fund_flow │ industry_analyzer                               │
├─────────────────────────────────────────────────────────────┤
│                  Infrastructure Layer                        │
│  PostgreSQL 17 │ Redis 7 │ ORM 27表 │ Alembic              │
│  data_manager │ quote_adapter (Fallback)                    │
│  event_bus │ notification_hub (4通道)                        │
├─────────────────────────────────────────────────────────────┤
│                     DevOps Layer                             │
│  Docker │ GitHub Actions CI │ 248 tests │ ruff              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 模組功能清單

| 模組 | 功能 | 檔案 | 測試覆蓋 |
|------|------|------|---------|
| scoring_engine | 四主軸評分 + 三面向驗證 | `atlas/strategy/scoring_engine.py` | ✅ |
| conclusion_engine | 七級結論 + 三層降級 | `atlas/application/conclusion_engine.py` | ✅ |
| screener_engine | Universe→Score→Rank→TopN | `atlas/application/screener_engine.py` | ✅ |
| indicator_lib | MA/RSI/MACD/BB/ATR/KD/OBV/VP | `atlas/strategy/indicator_lib.py` | ✅ |
| smc_module | Order Blocks/FVG/Sweep/CRT | `atlas/strategy/smc_module.py` | ✅ |
| ml_engine | RandomForest 預測 + 特徵重要度 | `atlas/strategy/ml_engine.py` | ✅ |
| monte_carlo | 蒙地卡羅模擬 | `atlas/strategy/monte_carlo.py` | ✅ |
| realtime_radar | 11 偵測器 + 6 盤中訊號 | `atlas/application/realtime_radar.py` | ✅ |
| backtest_engine | Walk-forward + 參數掃描 + 成本 | `atlas/application/backtest_engine.py` | ✅ |
| paper_trading | 模擬交易 + 手續費/證交稅 | `atlas/application/paper_trading.py` | ✅ |
| workflow_engine | 盤前/盤中/盤後 SOP | `atlas/application/workflow_engine.py` | ✅ |
| market_regime | 牛/熊/盤整三態 | `atlas/domain/market_regime.py` | ✅ |
| sentiment | 五級情緒 | `atlas/domain/sentiment.py` | ✅ |
| portfolio | R-multiple 風控 | `atlas/domain/portfolio.py` | ✅ |
| fund_flow | 法人資金流向 | `atlas/domain/fund_flow.py` | ✅ |
| notification_hub | Discord/LINE/Telegram/Email | `atlas/infrastructure/notification_hub.py` | ✅ |
| quote_adapter | TWSE MIS → yfinance → cache | `atlas/infrastructure/quote_adapter.py` | ✅ |
| data_manager | TWSE/TPEx/yfinance Fallback | `atlas/infrastructure/data_manager.py` | ✅ |

---

## 五、差異分析矩陣

### 5.1 完全缺失的功能（紅色 — 建議新增）

| # | 功能 | 來源文件 | 說明 | 預估影響 | 優先級 |
|---|------|---------|------|---------|--------|
| A1 | **因子探勘管線** | 06 | IC/ICIR 自動評估 + 因子生命週期管理（觀察→候選→核心→衰退→淘汰）+ Benjamini-Hochberg 校正 + HTML 互動報告 | 選股品質自進化 | **P0** |
| A2 | **開盤缺口預測** | 16 | ADR漲跌% + 費半% + ES夜盤 → 加權缺口預測 → gap_forecast.json → 盤後校驗閉環 | 盤前決策完整度 | **P0** |
| A3 | **Qullamaggie 突破策略** | qullamaggie | 客觀規則層（200MA+動能+收縮+RSI）+ Market Regime 動態權重（Bull/Normal/Recovery/Bear）+ 催化劑評分(1-10) + 分段獲利 + 假突破偵測 | 策略多元性 | **P1** |
| A4 | **外匯監控模組** | TECHNICAL_forex | 五大貨幣對匯率追蹤 + 套息交易分析 + 財經事件日曆 + 台股匯率連動提示（匯率敏感股推薦） | 總經維度補充 | **P1** |
| A5 | **主力階段偵測** | TECHNICAL_webapp | 四階段判定（吸籌/洗盤/拉升/出貨）+ 四維度加權（量能30%+價格30%+均線20%+動能20%）+ 案例比對五種型態 | 個股生命週期定位 | **P1** |
| A6 | **開盤意圖判斷** | TECHNICAL_webapp | 7 種開盤分類（強勢拉升/開高走低/試探/洗後承接/賣壓/偷吃貨/中性）+ 30 分價動向 + 量能比 + 大單方向 | 盤中第一手判斷 | **P2** |
| A7 | **交易價位計算** | TECHNICAL_webapp | 支撐壓力位 + 費波那契回撤(23.6%/38.2%/50%/61.8%) + 風險報酬比 + 建議買點（回踩買+突破買） | 進出場紀律 | **P1** |
| A8 | **REST API 層** | API.md | 20+ 端點（儀表板/選股/個股判讀/訊號/監控/匯率/Checklist）+ CORS + 背景任務 | 外部系統整合 | **P2** |
| A9 | **群益 Capital 下單** | 20 | SKCOM.dll 整合 + 半自動下單（LINE Bot Flex 確認→委託）+ 五重風控（處置股/次數/金額/停損/冷卻） | 真實交易能力 | **P2** |
| A10 | **天天回測勝率篩選** | 20 | 每日 15:30 全策略回測 + 自動停用低勝率策略（勝率<55% or EV<0.3% or 樣本<20 or MDD>15%） | 策略自我淘汰 | **P1** |

### 5.2 有基礎但需強化的功能（黃色）

| # | 功能 | 現狀 | 參考強化方向 | 差距程度 | 優先級 |
|---|------|------|-------------|---------|--------|
| B1 | **波浪葛蘭碧整合** | scoring_engine 有基礎技術面評估 | 07: 三層 MA 完整架構 + 葛蘭碧八法星級評分(★~★★★) + 9宮格訊號強度矩陣 + 活動靶系統 | 大（缺核心矩陣） | **P0** |
| B2 | **飆股訊號** | scoring_engine 概念存在 | 08: 完整 N字底四要素偵測 + 6字訣趨勢評分 + 均線排列完美度(0-4分) + 量價配合門檻(1.2x均量) | 中（缺偵測邏輯） | **P1** |
| B3 | **多流派共識** | conclusion_engine 七級結論 | 10/17: SignalStrength 結構化 + 訊號×飆股一致性檢查 + 衝突標記(conflict_flags) + 降級可追溯(downgrade_sources) | 大（缺衝突仲裁） | **P0** |
| B4 | **UI 設計系統** | Streamlit 基礎樣式 | 14: TradingView 深色主題 8 token + 買入卡片左色條 + 流派卡片藍邊框 + tabular-nums + 市場狀態列 | 中（純 CSS 層） | **P1** |
| B5 | **盤中雷達** | realtime_radar 11 偵測器 | 02/07: 盤中蕭明道六訊號(B1-B3/S1-S3) + B2/S2 互斥規則 + 漲跌停互斥 | 小（增互斥規則） | **P1** |
| B6 | **選股矛盾修復** | scoring + conclusion 雙軌 | 17: 12 項矛盾修復（詳見第八節） | 大（架構層級） | **P0** |
| B7 | **ML 引擎** | ml_engine (RandomForest) | MasterTalks: 20+ 特徵工程 + 防未來函數三層檢查(assert_no_lookahead) + signal.shift(1) + 台股成本 0.685% | 中（缺防護機制） | **P1** |
| B8 | **回測引擎** | backtest_engine (walk-forward) | 00/04: 4 種回測模式(+Compare/風險層) + 移動停損時序 + 過度擬合排查清單 + CSV Log | 中（缺模式） | **P2** |
| B9 | **市場環境** | market_regime + sentiment | 00: 三層判斷（趨勢+情緒五因子+寬度指標）+ ATR 倉位計算 + 情緒感知停損 | 中（缺寬度指標） | **P1** |
| B10 | **通知推送** | notification_hub 四通道 | 05/20: Log 監控→解析→去重 + Discord/LINE Bot 雙管道分工策略 | 小（增去重） | **P2** |
| B11 | **雲端部署** | Docker + GitHub Actions | 20: 本地+雲端雙軌(SQLite→TiDB Cloud) + Render Dashboard + Backblaze 備份 + Uptime Robot 保活 | 中（缺備援） | **P2** |

### 5.3 已充分覆蓋的功能（綠色）

| 功能 | Atlas 實作 | 參考對應 | 品質評估 |
|------|-----------|---------|---------|
| 四軸選股 (產業→題材→資金→RS) | scoring_engine.py | 00, 01 | ✅ 架構正確，待接入真實資料 |
| 技術指標 (MA/RSI/MACD/BB/ATR/KD) | indicator_lib.py | 03, 10 | ✅ 12 種指標 |
| SMC (Order Blocks/FVG/Sweep/CRT) | smc_module.py | system_introduction | ✅ 超越參考來源 |
| 蒙地卡羅模擬 | monte_carlo.py | Stock_Strategy_intro | ✅ 完整實作 |
| 結論七級系統 | conclusion_engine.py | 10, system_intro | ✅ 但需修復矛盾 |
| 產業輪動分析 | industry_analyzer.py | 00 | ✅ 基礎完整 |
| 法人資金流向 | fund_flow.py | 01, TECHNICAL_webapp | ✅ 五維評分 |
| 即時報價 Fallback | quote_adapter.py | Stock_Strategy_intro | ✅ TWSE→yfinance→cache |
| Paper Trading | paper_trading.py | 04 | ✅ 含手續費/證交稅 |
| 排程自動化 | scheduler + workflow | 20, system_intro | ✅ APScheduler cron |
| 多通道通知 | notification_hub.py | 05 | ✅ Discord/LINE/TG/Email Fallback |
| R-multiple 風控 | portfolio.py | Stock_Strategy_intro | ✅ 完整實作 |
| 11 偵測器 | realtime_radar.py | 00, 02 | ✅ 100% 覆蓋 |
| 13 頁 UI | presentation/pages/ | Atlas_操作手冊 | ✅ 完整 |

---

## 六、量化差距統計

### 6.1 功能覆蓋率雷達圖（文字版）

```
                        選股策略 (47%)
                            │
              通知(100%)──────┼──────技術指標(60%)
                   │         │         │
           UI分頁(100%)──────┼──────擴充模組(67%)
                   │         │         │
           偵測器(100%)──────┼──────回測模式(50%)
                             │
              REST API(0%) ──┼── 因子探勘(0%)
                             │
              外匯(0%) ──────┼── 缺口預測(0%)
                             │
                      主力階段(0%)
```

### 6.2 精確數據表

| 維度 | 參考來源總計 | Atlas 已有 | 覆蓋率 | 缺口項目 |
|------|------------|-----------|--------|---------|
| 選股策略/流派 | 15 套 | 7 套 | **47%** | 波浪完整版/飆股完整版/Qullamaggie/O'Neil16分/七維度/Weinstein/Darvas/因子組合 |
| 技術指標 | 20+ 種 | 12 種 | **60%** | 費波那契回撤/Weinstein 階段/Darvas 箱型/扣抵共振/角度企圖 |
| 擴充模組 | 9 個 | 6 個 | **67%** | 費波那契/Weinstein/Darvas |
| 盤中偵測器 | 11 個 | 11 個 | **100%** | — |
| 回測模式 | 4 種 | 2 種 | **50%** | Compare 模式/風險層模式 |
| 通知管道 | 4 管道 | 4 管道 | **100%** | — |
| UI 分頁 | 13 頁 | 13 頁 | **100%** | — |
| REST API | 20+ 端點 | 0 | **0%** | 全缺（僅 Streamlit） |
| 自動交易/下單 | 群益+XQ | Paper Trading | **~30%** | 真實下單/移動停損 |
| 因子探勘 | 完整管線 | 無 | **0%** | IC/ICIR/生命週期 |
| 缺口預測 | 完整模組 | 無 | **0%** | ADR+費半→預測 |
| 外匯模組 | 完整系統 | 無 | **0%** | 匯率+套息+連動 |
| 主力階段 | 4 階段偵測 | 無 | **0%** | 吸籌/洗盤/拉升/出貨 |

### 6.3 加權綜合覆蓋率

按業務重要性加權：

| 維度 | 權重 | 覆蓋率 | 加權分 |
|------|------|--------|--------|
| 選股策略 | 25% | 47% | 11.75 |
| 技術指標 | 10% | 60% | 6.00 |
| 因子探勘 | 15% | 0% | 0.00 |
| 回測 | 10% | 50% | 5.00 |
| 即時偵測 | 10% | 100% | 10.00 |
| 下單執行 | 10% | 30% | 3.00 |
| UI/通知 | 5% | 100% | 5.00 |
| REST API | 5% | 0% | 0.00 |
| 缺口/外匯/主力 | 10% | 0% | 0.00 |
| **合計** | **100%** | — | **40.75/100** |

**Atlas v5.0 加權功能覆蓋率：40.75%**（架構優勢未計入，純功能維度）

---

## 七、跨系統架構比較

### 7.1 四套既有系統 vs Atlas v5.0

| 維度 | 台股AI看盤 (MasterTalks) | 選股系統 (Stock_Strategy) | Atlas Signal Radar (Mindao) | Signal Radar (XQdata) | **Atlas v5.0** |
|------|--------------------------|--------------------------|----------------------------|----------------------|----------------|
| **UI** | Gradio | Streamlit | Streamlit | Streamlit | **Streamlit** |
| **DB** | SQLite | 無(CSV/JSON) | 無(JSON cache) | 無(JSON cache) | **PostgreSQL 17 + Redis 7** |
| **ML** | RandomForest + 20特徵 | 無 | 無 | 無 | **RandomForest** |
| **策略數** | ML 分類 | O'Neil 16分 | 22 日K + 6 盤中 | 5層訊號+15流派 | **4軸+3面向+SMC** |
| **回測** | 含成本向量化 | 蒙地卡羅 | 基因優化 | 4 模式 | **Walk-forward + 參數掃描** |
| **通知** | Email | LINE + Telegram | Discord | Telegram | **Discord/LINE/TG/Email** |
| **即時行情** | 無 | TWSE MIS | 群益 SKCOM | 無 | **TWSE MIS → yfinance Fallback** |
| **測試** | 無 | 無 | 無 | 無 | **248 tests** |
| **CI/CD** | 無 | 無 | GitHub Actions | 無 | **GitHub Actions** |
| **容器化** | 無 | 無 | 無 | 無 | **Docker multi-stage** |
| **ORM** | 無 | 無 | 無 | 無 | **SQLAlchemy 2.0 (27表)** |

**結論**：Atlas v5.0 在**工程品質**上遠超所有參考系統（唯一有測試、CI、容器化、ORM 的系統），但在**策略深度**上仍需吸收各系統精華。

### 7.2 架構優勢分析

Atlas v5.0 的結構性優勢：

1. **五層分離架構**：Presentation → Application → Strategy → Domain → Infrastructure，擴充新策略不影響其他層
2. **介面抽象**（`atlas/interfaces/`）：所有核心服務定義 ABC，可替換實作
3. **事件驅動**（EventBus）：模組間鬆耦合，新增偵測器/通知通道不需改既有程式碼
4. **資料一致性**（PostgreSQL + ORM）：相比 JSON/CSV/SQLite，支援事務、索引、遷移
5. **Fallback 鏈設計**：quote_adapter、notification_hub 皆有多層備援
6. **測試覆蓋**（248 tests）：唯一有自動化測試的系統

---

## 八、風險與根因分析

### 8.1 Atlas v5.0 矛盾直接映射（來自 17 號文件）

| 矛盾 # | 原始描述 | Atlas 映射位置 | 嚴重度 | 說明 |
|---------|---------|---------------|--------|------|
| **M2** | 結論欄雙軌制 | `screener_engine.py:67-80` 複製 `conclusion_engine.py:50-66` | **P0** | 兩處獨立結論映射邏輯，screener 完全跳過三層降級 |
| **M5** | 擴充模組不進評分 | `ScanResult` 有 `ml_prediction`/`smc_confirmed`/`auxiliary_confidence` | **P1** | 三個欄位永遠是預設值(None/NA)，不影響結論 |
| **M6** | 降級不同步 | `screener_engine` 不呼叫 `conclusion_engine` | **P0** | screener 直接算結論，完全無降級機制 |
| **M11** | 缺結構化類型 | `enums.py` 無 `SignalStrength` | **P1** | 無訊號強度 Enum，無衝突偵測機制 |
| **M3/M8** | 衝突無仲裁 | 無 `conflict_flags` 概念 | **P0** | 矛盾訊號無法被發現和標記 |

### 8.2 根因分析

```
根因 1：結論引擎未被統一呼叫
├── screener_engine 自行映射結論（跳過 conclusion_engine）
├── 兩處結論邏輯獨立演化，分數區間不一致
└── 三層降級（大盤/情緒/產業）在選股流程中被完全跳過

根因 2：缺少結構化的訊號強度和衝突機制
├── 無 SignalStrength IntEnum（只有 ConclusionLevel）
├── 無 ConflictFlag 概念（無法標記矛盾訊號）
└── ScanResult 的輔助欄位未被使用

根因 3：評分體系與結論體系脫鉤
├── AxisScore.total_score 是 0-100 連續值
├── ConclusionLevel 是 -2~+5 的離散等級
└── 映射邏輯（>=80→LV5, >=70→LV4...）缺少訊號方向維度
```

---

## 九、優化與擴充建議

### 9.1 短期（Phase 11 — P0 核心修復）

#### 9.1.1 選股矛盾修復

**目標**：消滅雙軌結論，建立唯一真相源

**修改清單**：
| 檔案 | 修改內容 |
|------|---------|
| `atlas/enums.py` | 新增 `SignalStrength`(IntEnum, 7 級) + `ConflictFlag`(StrEnum) |
| `atlas/models/scoring.py` | `ConclusionResult` 加 `signal_strength`, `conflict_flags`, `downgrade_sources` |
| `atlas/application/conclusion_engine.py` | 加入訊號強度計算 + 衝突偵測 + 產業勝率降級 |
| `atlas/application/screener_engine.py` | 移除 L67-80 重複結論邏輯，改呼叫 `conclusion_engine.evaluate()` |
| `tests/unit/test_conclusion_engine.py` | 新增衝突偵測 + 降級追溯 + 邊界案例測試 |

#### 9.1.2 多流派共識強化

**目標**：加入訊號強度維度和衝突仲裁

**新增 Enum**：
```python
class SignalStrength(IntEnum):
    STRONG_BUY = 3    # ★★★ 強買
    BUY = 2           # ★★ 買進
    WEAK_BUY = 1      # ★ 弱買
    NEUTRAL = 0       # 觀望
    WEAK_SELL = -1    # ★ 弱賣
    SELL = -2         # ★★ 賣出
    STRONG_SELL = -3  # ★★★ 強賣

class ConflictFlag(StrEnum):
    COUNTER_TREND = "COUNTER_TREND"   # 逆勢訊號（短多長空）
    SIGNAL_CLASH = "SIGNAL_CLASH"     # 流派互斥
    VOLUME_DIVERGE = "VOLUME_DIVERGE" # 量價背離
```

#### 9.1.3 波浪葛蘭碧完整化

**目標**：補齊 9 宮格矩陣和八法星級

#### 9.1.4 因子探勘管線

**目標**：建立 IC/ICIR 自動評估 + 因子生命週期管理

**新增模組**：
| 檔案 | 功能 |
|------|------|
| `atlas/strategy/factor_mining.py` | IC/ICIR 計算 + 因子評估管線 |
| `atlas/models/factor.py` | Factor / FactorResult / FactorLifecycle dataclass |
| `atlas/infrastructure/orm/factor.py` | factor_registry / factor_evaluation ORM |

### 9.2 中期（Phase 12 — P1 策略擴充）

| # | 功能 | 新增/修改模組 | 預估工作量 |
|---|------|-------------|-----------|
| 1 | 開盤缺口預測 | `atlas/strategy/gap_predictor.py` | 中 |
| 2 | Qullamaggie 突破 | `atlas/strategy/qullamaggie.py` | 中 |
| 3 | 主力階段偵測 | `atlas/domain/phase_detector.py` | 大 |
| 4 | 交易價位計算 | `atlas/strategy/price_levels.py` | 小 |
| 5 | 天天回測篩選 | 修改 `backtest_engine.py` + `scheduler.py` | 中 |
| 6 | 飆股訊號完整化 | 修改 `scoring_engine.py` | 中 |
| 7 | UI TradingView 風格 | 修改 `presentation/components/theme.py` | 小 |
| 8 | ML 防未來函數 | 修改 `ml_engine.py` | 小 |
| 9 | 市場寬度指標 | 修改 `market_regime.py` | 中 |

### 9.3 長期（Phase 13 — P2 進階功能）

| # | 功能 | 說明 |
|---|------|------|
| 1 | 外匯監控 | 貨幣對+套息+台股連動 → 新 domain 模組 |
| 2 | 開盤意圖 | 7 種分類 → realtime_radar 擴充 |
| 3 | REST API | FastAPI server → 新 presentation 層 |
| 4 | 群益下單 | SKCOM.dll → 新 infrastructure 模組 |
| 5 | 雲端雙軌 | TiDB Cloud + Render + Backblaze |

---

## 十、實作路線圖

### 10.1 Phase 11：核心修復與補強（P0）

```
Week 1-2
├── B6 選股矛盾修復
│   ├── enums.py: +SignalStrength, +ConflictFlag
│   ├── models/scoring.py: ConclusionResult 擴充
│   ├── conclusion_engine.py: 衝突偵測 + 產業勝率降級
│   ├── screener_engine.py: 移除重複結論，統一呼叫 conclusion_engine
│   └── tests: 衝突 mock 驗證
│
├── B3 多流派共識強化
│   ├── 訊號強度 × 結論一致性檢查
│   └── 降級可追溯（downgrade_sources 列表）
│
Week 3-4
├── B1 波浪葛蘭碧完整化
│   ├── 葛蘭碧八法星級評分
│   ├── 9 宮格訊號強度矩陣
│   └── 活動靶系統
│
└── A1 因子探勘管線
    ├── factor_mining.py: IC/ICIR 計算
    ├── 因子生命週期管理
    └── HTML 報告生成
```

### 10.2 Phase 12：策略擴充（P1）

```
Week 5-6
├── A2 開盤缺口預測
├── A3 Qullamaggie 突破策略
└── A10 天天回測篩選

Week 7-8
├── A5 主力階段偵測
├── A7 交易價位計算
├── B2 飆股訊號完整化
└── B4 UI TradingView 風格
```

### 10.3 Phase 13：進階功能（P2）

```
Week 9+（持續迭代）
├── A4 外匯監控
├── A6 開盤意圖
├── A8 REST API (FastAPI)
├── A9 群益 Capital 下單
└── B11 雲端雙軌部署
```

### 10.4 依賴關係圖

```
B6 選股矛盾修復 ──────→ B3 多流派共識 ──────→ A10 天天回測篩選
       │                                           │
       └──→ B1 波浪葛蘭碧 ──→ B2 飆股完整化        │
                                                    │
A1 因子探勘 ─────→ (獨立，可平行)                    │
                                                    │
A2 缺口預測 ─────→ (獨立，可平行)                    │
                                                    │
A5 主力階段 ─────→ A6 開盤意圖                      │
                                                    │
A7 交易價位 ─────→ (獨立)                            │
                                                    ▼
                                           A9 群益下單（需 B6+A10 完成）
```

---

## 十一、結論

### 11.1 Atlas v5.0 的競爭優勢

Atlas v5.0 在**工程架構品質**上是所有系統中最強的：
- 唯一有五層分離架構、ABC 介面抽象、EventBus 事件驅動
- 唯一有 PostgreSQL + Redis + Docker + CI/CD + 248 tests
- 唯一有 ORM 遷移（Alembic 27 表）和完整 Fallback 鏈

### 11.2 最大弱點

**策略深度不足**（覆蓋率 47%）和**缺乏自進化能力**（因子探勘 0%）是兩個最大缺口。架構再好，如果策略品質不足，交易結果不會好。

### 11.3 三個最高 ROI 行動

| 優先級 | 行動 | ROI 理由 |
|--------|------|---------|
| 1️⃣ | **修復選股矛盾** | 確保現有功能正確性，避免矛盾訊號誤導決策。不修復等於「用壞掉的引擎開車」 |
| 2️⃣ | **因子探勘管線** | 從手工定規則升級為數據驅動，讓系統能自動發現和淘汰失效因子。這是從「工具」到「平台」的關鍵跳躍 |
| 3️⃣ | **開盤缺口預測** | 盤前工作流的最後一塊拼圖，直接提升每日第一個交易決策的品質 |

### 11.4 預估完成後的覆蓋率提升

| 階段 | 覆蓋率 | 提升 |
|------|--------|------|
| 現在 | 40.75% | — |
| Phase 11 完成後 | **58%** | +17.25% |
| Phase 12 完成後 | **78%** | +20% |
| Phase 13 完成後 | **92%** | +14% |

---

> **文件結束**
> 下一步：按 Phase 11 路線圖開始實作，首先處理 B6 選股矛盾修復。
