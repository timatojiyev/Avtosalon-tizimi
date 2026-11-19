"""Hisobotlar: servislardan olingan ma'lumotlar bo'yicha KPI'lar va SVG diagrammalar (tashqi JS/CDN'siz)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from markupsafe import Markup, escape

PALETTE = ["#c2410c", "#2563eb", "#16a34a", "#7c3aed", "#db2777", "#0891b2", "#ca8a04", "#64748b"]
STATUS_LABEL = {"boshlangan": "Boshlangan", "kredit_tasdiqlangan": "Kredit tasdiqlangan", "kredit_rad_etilgan": "Kredit rad etilgan",
                "yakunlangan": "Yakunlangan", "bekor_qilingan": "Bekor qilingan"}


def short_som(v: float) -> str:
    v = float(v or 0)
    if v >= 1e9:
        return f"{v / 1e9:.2f} mlrd".replace(".00", "")
    if v >= 1e6:
        return f"{v / 1e6:.0f} mln"
    return f"{int(v):,}".replace(",", " ")


def _day(iso: str | None) -> date | None:
    try:
        return datetime.fromisoformat(str(iso)).date()
    except (TypeError, ValueError):
        return None


def build_report(sales: list[dict[str, Any]], cars: list[dict[str, Any]], apps: list[dict[str, Any]], days: int = 14) -> dict[str, Any]:
    done = [s for s in sales if s["status"] == "yakunlangan"]
    closed = [s for s in sales if s["status"] in ("yakunlangan", "bekor_qilingan", "kredit_rad_etilgan")]
    revenue = sum(int(s["price"]) for s in done)
    approved = [a for a in apps if a["status"] == "tasdiqlandi"]
    kpi = {
        "revenue": revenue,
        "deals": len(done),
        "avg_check": revenue // len(done) if done else 0,
        "conversion": round(len(done) / len(closed) * 100, 1) if closed else 0.0,
        "pipeline": sum(int(s["price"]) for s in sales if s["status"] in ("boshlangan", "kredit_tasdiqlangan")),
        "approval_rate": round(len(approved) / len(apps) * 100, 1) if apps else 0.0,
        "avg_pti": round(sum(float(a["pti"]) for a in apps) / len(apps), 1) if apps else 0.0,
        "financed": sum(int(a["amount"]) for a in approved),
        "stock_value": sum(int(c["price"]) for c in cars if c["status"] == "sotuvda"),
        "stock_count": sum(1 for c in cars if c["status"] == "sotuvda"),
        "total_sales": len(sales),
    }

    today = date.today()
    daily = defaultdict(int)
    for s in done:
        d = _day(s.get("updated_at"))
        if d:
            daily[d] += int(s["price"])
    series = [((today - timedelta(days=i)), daily.get(today - timedelta(days=i), 0)) for i in range(days - 1, -1, -1)]

    by_brand: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for s in done:
        brand = str(s["car_title"]).split(" ")[0]
        by_brand[brand][0] += 1
        by_brand[brand][1] += int(s["price"])
    brands = sorted(by_brand.items(), key=lambda kv: -kv[1][1])

    status = Counter(s["status"] for s in sales)
    methods = Counter(s["payment_method"] for s in sales)
    funnel = [("Boshlangan sotuvlar", len(sales)),
              ("Kreditga murojaat", methods.get("kredit", 0)),
              ("Kredit tasdiqlandi", len(approved)),
              ("Yakunlangan", len(done))]
    managers = Counter(s.get("customer_name", "—") for s in done)
    return {"kpi": kpi, "daily": series, "brands": brands, "status": status, "methods": methods, "funnel": funnel,
            "top_customers": managers.most_common(5)}


# ---------------- SVG ----------------
def bar_chart(series: list[tuple[date, int]], width: int = 720, height: int = 240) -> Markup:
    pad_l, pad_b, pad_t = 56, 28, 12
    w, h = width - pad_l - 8, height - pad_b - pad_t
    peak = max((v for _, v in series), default=0) or 1
    step = w / max(len(series), 1)
    bw = step * 0.62
    out = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="Kunlik tushum">']
    for i in range(5):
        y = pad_t + h - h * i / 4
        out.append(f'<line x1="{pad_l}" x2="{width - 8}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{pad_l - 6}" y="{y + 4:.1f}" class="axis" text-anchor="end">{escape(short_som(peak * i / 4))}</text>')
    for i, (d, v) in enumerate(series):
        x = pad_l + i * step + (step - bw) / 2
        bh = h * v / peak
        out.append(f'<rect x="{x:.1f}" y="{pad_t + h - bh:.1f}" width="{bw:.1f}" height="{max(bh, 0.5):.1f}" rx="3" class="bar">'
                   f'<title>{d:%d.%m}: {escape(short_som(v))} so\'m</title></rect>')
        if len(series) <= 16 or i % 2 == 0:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{height - 8}" class="axis" text-anchor="middle">{d:%d.%m}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def donut(parts: list[tuple[str, int]], size: int = 170) -> Markup:
    total = sum(v for _, v in parts) or 1
    r, c = size / 2 - 14, size / 2
    circ = 2 * 3.14159265 * r
    out = [f'<svg viewBox="0 0 {size} {size}" class="chart donut" role="img">']
    out.append(f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="var(--muted-bg)" stroke-width="22"/>')
    offset = 0.0
    for i, (label, v) in enumerate(parts):
        if not v:
            continue
        seg = circ * v / total
        out.append(f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{PALETTE[i % len(PALETTE)]}" stroke-width="22"'
                   f' stroke-dasharray="{seg:.2f} {circ - seg:.2f}" stroke-dashoffset="{-offset:.2f}"'
                   f' transform="rotate(-90 {c} {c})"><title>{escape(label)}: {v}</title></circle>')
        offset += seg
    out.append(f'<text x="{c}" y="{c - 2}" text-anchor="middle" class="donut-value">{sum(v for _, v in parts)}</text>'
               f'<text x="{c}" y="{c + 16}" text-anchor="middle" class="axis">jami</text></svg>')
    return Markup("".join(out))
