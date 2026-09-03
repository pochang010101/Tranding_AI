"""個股分析圖表元件 — 雷達圖、圓環儀表、多空能量、預測扇形、籌碼熱區、法人流向。"""

from __future__ import annotations

import math

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from atlas.presentation.components.theme import get_colors


# ── 共用工具 ────────────────────────────────────────

def _score_color(value: int | float) -> str:
    """依分數回傳色碼：>= 80 綠, >= 60 橘, < 60 紅。"""
    if value >= 80:
        return "#00c853"
    if value >= 60:
        return "#ff9100"
    return "#ff1744"


def _base_layout(fig: go.Figure, title: str, height: int) -> go.Figure:
    """統一圖表佈局（透明背景、緊湊 margin）。"""
    c = get_colors()
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        template=c["plotly_template"],
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor=c["plotly_paper"],
        font=dict(family="Microsoft JhengHei, sans-serif", color=c["text_primary"]),
        height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


# ── 1. 多維雷達圖 ──────────────────────────────────

def radar_chart(
    categories: list[str],
    values: list[int],
    title: str = "多維度判讀",
    overall_score: int | None = None,
    overall_grade: str | None = None,
    height: int = 350,
) -> go.Figure:
    """多維度雷達圖，中心顯示總分與等級。"""
    avg = sum(values) / len(values) if values else 0
    color = _score_color(avg)

    # 閉合多邊形
    cats = list(categories) + [categories[0]]
    vals = list(values) + [values[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals,
        theta=cats,
        fill="toself",
        fillcolor=color.replace("#", "rgba(") + ")" if False else f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},0.15)",
        line=dict(color=color, width=2),
        marker=dict(size=6, color=color),
        name="評分",
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=10)),
            angularaxis=dict(tickfont=dict(size=12)),
        ),
    )

    # 中心 annotation：總分 + 等級
    if overall_score is not None:
        grade_text = f"{overall_grade} " if overall_grade else ""
        fig.add_annotation(
            text=f"<b>{grade_text}{overall_score}/100</b>",
            x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=22, color=_score_color(overall_score)),
        )

    return _base_layout(fig, title, height)


# ── 2. 健康度圓環組 ────────────────────────────────

def gauge_rings(
    metrics: list[dict],
    columns: int = 5,
    height: int = 200,
) -> go.Figure:
    """多指標圓環儀表組，每個 metric 為 {"name": str, "value": int}。"""
    n = len(metrics)
    cols = min(columns, n)
    rows = math.ceil(n / cols)

    fig = make_subplots(
        rows=rows, cols=cols,
        specs=[[{"type": "pie"} for _ in range(cols)] for _ in range(rows)],
        horizontal_spacing=0.03,
        vertical_spacing=0.08,
    )

    for i, m in enumerate(metrics):
        r = i // cols + 1
        c_idx = i % cols + 1
        val = m["value"]
        color = _score_color(val)
        remainder = 100 - val

        fig.add_trace(go.Pie(
            values=[val, remainder],
            hole=0.7,
            marker=dict(colors=[color, "rgba(128,128,128,0.15)"]),
            textinfo="none",
            hoverinfo="label+value",
            showlegend=False,
            name=m["name"],
        ), row=r, col=c_idx)

        # 中心百分比 + 名稱（用 annotation 定位到子圖中心）
        # 計算子圖中心座標
        x_start = (c_idx - 1) / cols
        x_end = c_idx / cols
        y_start = 1 - r / rows
        y_end = 1 - (r - 1) / rows
        cx = (x_start + x_end) / 2
        cy = (y_start + y_end) / 2

        fig.add_annotation(
            text=f"<b>{val}%</b><br><span style='font-size:10px'>{m['name']}</span>",
            x=cx, y=cy, xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=14, color=color),
        )

    return _base_layout(fig, "", height)


# ── 3. 多空能量條 ──────────────────────────────────

def energy_bar(
    bull_pct: float,
    bear_pct: float,
    title: str = "多空能量",
    height: int = 80,
) -> go.Figure:
    """水平堆疊多空能量條，左紅（多）右綠（空）。"""
    c = get_colors()

    # 多空比計算
    if bear_pct > 0:
        ratio = bull_pct / bear_pct
        side = "多" if ratio >= 1 else "空"
        ratio_text = f"多空比：{ratio:.2f} 倍{side}"
    else:
        ratio_text = "多空比：全多"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[bull_pct], y=["能量"],
        orientation="h",
        marker_color=c["positive"],
        name="多方",
        text=[f"{bull_pct:.1f}%"],
        textposition="inside",
        textfont=dict(size=14, color="white"),
    ))
    fig.add_trace(go.Bar(
        x=[bear_pct], y=["能量"],
        orientation="h",
        marker_color=c["negative"],
        name="空方",
        text=[f"{bear_pct:.1f}%"],
        textposition="inside",
        textfont=dict(size=14, color="white"),
    ))

    fig.update_layout(
        barmode="stack",
        xaxis=dict(visible=False, range=[0, 100]),
        yaxis=dict(visible=False),
        showlegend=False,
    )

    fig.add_annotation(
        text=f"<b>{ratio_text}</b>",
        x=0.5, y=-0.3, xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=12, color=c["text_secondary"]),
    )

    return _base_layout(fig, title, height)


# ── 4. AI 預測路徑圖（扇形機率帶）──────────────────

def prediction_fan_chart(
    current_price: float,
    bull_prob: float,
    range_prob: float,
    bear_prob: float,
    atr: float,
    days: int = 10,
    title: str = "AI 預測路徑",
    height: int = 350,
) -> go.Figure:
    """三路徑扇形預測圖：上漲(紅帶)、盤整(黃帶)、下跌(綠帶)。"""
    c = get_colors()
    x_days = [0, 3, 5, days]
    x_labels = ["今日", "3日後", "5日後", f"{days}日後"]

    def _path(slope: float, width_factor: float):
        """產生上下界路徑。"""
        upper, lower = [], []
        for d in x_days:
            center = current_price + slope * d * atr * 0.3
            spread = width_factor * atr * (d ** 0.5) * 0.5
            upper.append(center + spread)
            lower.append(center - spread)
        return upper, lower

    # 上漲路徑
    bull_upper, bull_lower = _path(1.0, 1.2)
    # 盤整路徑
    range_upper, range_lower = _path(0.0, 0.6)
    # 下跌路徑
    bear_upper, bear_lower = _path(-1.0, 1.2)

    fig = go.Figure()

    # 上漲帶（紅 = positive = 漲）
    fig.add_trace(go.Scatter(
        x=x_labels + x_labels[::-1],
        y=bull_upper + bull_lower[::-1],
        fill="toself",
        fillcolor=f"rgba({int(c['positive'][1:3], 16)},{int(c['positive'][3:5], 16)},{int(c['positive'][5:7], 16)},0.15)",
        line=dict(color=c["positive"], width=1),
        name=f"上漲 {bull_prob*100:.0f}%",
    ))

    # 盤整帶（黃）
    fig.add_trace(go.Scatter(
        x=x_labels + x_labels[::-1],
        y=range_upper + range_lower[::-1],
        fill="toself",
        fillcolor="rgba(255,145,0,0.15)",
        line=dict(color=c["warning"], width=1),
        name=f"盤整 {range_prob*100:.0f}%",
    ))

    # 下跌帶（綠 = negative = 跌）
    fig.add_trace(go.Scatter(
        x=x_labels + x_labels[::-1],
        y=bear_upper + bear_lower[::-1],
        fill="toself",
        fillcolor=f"rgba({int(c['negative'][1:3], 16)},{int(c['negative'][3:5], 16)},{int(c['negative'][5:7], 16)},0.15)",
        line=dict(color=c["negative"], width=1),
        name=f"下跌 {bear_prob*100:.0f}%",
    ))

    # 當前價格水平線
    fig.add_hline(
        y=current_price, line_dash="dash",
        line_color=c["text_secondary"], line_width=1,
        annotation_text=f"現價 {current_price:.1f}",
        annotation_font_size=11,
    )

    fig.update_layout(
        yaxis=dict(title="價格", gridcolor=c["plotly_grid"]),
        xaxis=dict(gridcolor=c["plotly_grid"]),
    )

    return _base_layout(fig, title, height)


# ── 5. 籌碼熱區圖（成本分布）──────────────────────

def volume_profile_chart(
    price_levels: list[float],
    volumes: list[float],
    current_price: float,
    support: float | None = None,
    resistance: float | None = None,
    title: str = "成本分布圖",
    height: int = 350,
) -> go.Figure:
    """水平柱狀籌碼分布圖（價格 Y 軸，量 X 軸），標註關鍵價位。"""
    c = get_colors()

    max_vol = max(volumes) if volumes else 1
    # 顏色漸層：低量藍 → 高量紅
    colors = []
    for v in volumes:
        ratio = v / max_vol
        r = int(30 + 225 * ratio)
        g = int(136 - 100 * ratio)
        b = int(229 - 180 * ratio)
        colors.append(f"rgb({r},{g},{b})")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=volumes,
        y=price_levels,
        orientation="h",
        marker_color=colors,
        name="成交量分布",
        opacity=0.85,
    ))

    # 當前價格線
    fig.add_hline(
        y=current_price, line_dash="solid",
        line_color=c["text_primary"], line_width=2,
        annotation_text=f"現價 {current_price:.1f}",
        annotation_position="top right",
        annotation_font=dict(size=11, color=c["text_primary"]),
    )

    # 支撐位
    if support is not None:
        fig.add_hline(
            y=support, line_dash="dash",
            line_color="#00c853", line_width=1.5,
            annotation_text=f"支撐 {support:.1f}",
            annotation_position="bottom right",
            annotation_font=dict(size=11, color="#00c853"),
        )

    # 壓力位
    if resistance is not None:
        fig.add_hline(
            y=resistance, line_dash="dash",
            line_color="#ff1744", line_width=1.5,
            annotation_text=f"壓力 {resistance:.1f}",
            annotation_position="top right",
            annotation_font=dict(size=11, color="#ff1744"),
        )

    # 標註大量成交區（最高量的價格帶）
    if volumes:
        peak_idx = volumes.index(max_vol)
        fig.add_annotation(
            text="大量成交區",
            x=max_vol * 0.7,
            y=price_levels[peak_idx],
            showarrow=True, arrowhead=2, arrowcolor=c["warning"],
            font=dict(size=11, color=c["warning"]),
        )

    # 套牢區 / 支撐區標註
    if resistance is not None and current_price < resistance:
        fig.add_annotation(
            text="套牢區",
            x=max_vol * 0.3, y=resistance,
            showarrow=False,
            font=dict(size=10, color="#ff1744"),
        )
    if support is not None and current_price > support:
        fig.add_annotation(
            text="支撐區",
            x=max_vol * 0.3, y=support,
            showarrow=False,
            font=dict(size=10, color="#00c853"),
        )

    fig.update_layout(
        xaxis=dict(title="成交量", gridcolor=c["plotly_grid"]),
        yaxis=dict(title="價格", gridcolor=c["plotly_grid"]),
    )

    return _base_layout(fig, title, height)


# ── 6. 法人買賣超組合圖 ───────────────────────────

def institutional_flow_chart(
    dates: list[str],
    foreign: list[int],
    trust: list[int],
    dealer: list[int],
    total: list[int],
    title: str = "三大法人買賣超",
    height: int = 350,
) -> go.Figure:
    """外資/投信/自營柱狀 + 合計折線，右下角標註累積偏多空。"""
    c = get_colors()

    fig = go.Figure()

    # 三大法人柱狀（grouped）
    fig.add_trace(go.Bar(
        x=dates, y=foreign, name="外資",
        marker_color="#2196f3", opacity=0.85,
    ))
    fig.add_trace(go.Bar(
        x=dates, y=trust, name="投信",
        marker_color="#ff9800", opacity=0.85,
    ))
    fig.add_trace(go.Bar(
        x=dates, y=dealer, name="自營商",
        marker_color="#4caf50", opacity=0.85,
    ))

    # 合計折線
    fig.add_trace(go.Scatter(
        x=dates, y=total, name="合計",
        mode="lines+markers",
        line=dict(color="#e91e63", width=2.5),
        marker=dict(size=5),
    ))

    fig.update_layout(
        barmode="group",
        xaxis=dict(gridcolor=c["plotly_grid"]),
        yaxis=dict(title="張數", gridcolor=c["plotly_grid"]),
    )

    # 累積買賣超判定
    cumulative = sum(total)
    bias = "偏多" if cumulative > 0 else "偏空" if cumulative < 0 else "中性"
    bias_color = c["positive"] if cumulative > 0 else c["negative"] if cumulative < 0 else c["neutral"]
    fig.add_annotation(
        text=f"<b>累積買賣超：{bias}</b>",
        x=1.0, y=0.0, xref="paper", yref="paper",
        xanchor="right", yanchor="bottom",
        showarrow=False,
        font=dict(size=12, color=bias_color),
        bgcolor="rgba(0,0,0,0.3)",
        borderpad=6,
    )

    return _base_layout(fig, title, height)
