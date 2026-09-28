"""Inline SVG charts generated in Python (no JS libraries). Tooltips via <title>."""

from __future__ import annotations

import math
from datetime import date

from markupsafe import Markup, escape

MONTHS_SHORT = ["sij", "velj", "ožu", "tra", "svi", "lip", "srp", "kol", "ruj", "lis", "stu", "pro"]


def _nice_max(value: float) -> int:
    """Round the axis maximum up to 1/2/5 × 10^n."""
    if value <= 0:
        return 5
    exponent = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 5, 10):
        if value <= step * exponent:
            return int(step * exponent)
    return int(10 * exponent)


def _divisions(max_value: int) -> int:
    """Number of y-axis intervals so that every tick is a whole number."""
    if max_value % 4 == 0:
        return 4
    if max_value % 5 == 0:
        return 5
    return max(1, min(max_value, 4))


def _y_axis(
    max_value: int, pad_left: int, width: int, pad_right: int, pad_top: int, inner_h: float
) -> list[str]:
    parts = []
    steps = _divisions(max_value)
    for i in range(steps + 1):
        value = max_value * i // steps
        y = pad_top + inner_h - inner_h * i / steps
        label = f"{value:,}".replace(",", ".")
        parts.append(
            f'<line class="chart-grid" x1="{pad_left}" x2="{width - pad_right}" '
            f'y1="{y:.1f}" y2="{y:.1f}"/><text class="chart-label" x="{pad_left - 6}" '
            f'y="{y + 4:.1f}" text-anchor="end">{label}</text>'
        )
    return parts


def bar_chart(
    points: list[tuple[date, int]],
    title: str,
    width: int = 760,
    height: int = 240,
    unit: str = "pregleda",
) -> Markup:
    """Vertical bar chart for daily values. `points` = [(day, value), ...] (chronological)."""
    pad_left, pad_right, pad_top, pad_bottom = 44, 12, 14, 30
    inner_w = width - pad_left - pad_right
    inner_h = height - pad_top - pad_bottom
    max_value = _nice_max(max((v for _, v in points), default=0))
    n = max(1, len(points))
    slot = inner_w / n
    bar_w = max(2.0, slot * 0.72)
    label_every = max(1, math.ceil(n / 10))

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(title)}" preserveAspectRatio="none">',
        f"<title>{escape(title)}</title>",
    ]
    parts += _y_axis(max_value, pad_left, width, pad_right, pad_top, inner_h)
    for index, (day, value) in enumerate(points):
        bar_h = inner_h * value / max_value if max_value else 0
        x = pad_left + index * slot + (slot - bar_w) / 2
        y = pad_top + inner_h - bar_h
        day_text = day.strftime("%d.%m.%Y.")
        parts.append(
            f'<rect class="chart-bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{max(bar_h, 0.5):.1f}" rx="2"><title>{day_text}: {value} {escape(unit)}'
            f"</title></rect>"
        )
        if index % label_every == 0 or index == n - 1:
            parts.append(
                f'<text class="chart-label" x="{x + bar_w / 2:.1f}" y="{height - 10}" '
                f'text-anchor="middle">{day.strftime("%d.%m.")}</text>'
            )
    parts.append(
        f'<line class="chart-axis" x1="{pad_left}" x2="{width - pad_right}" '
        f'y1="{pad_top + inner_h}" y2="{pad_top + inner_h}"/>'
    )
    parts.append("</svg>")
    return Markup("".join(parts))


def paired_bar_chart(
    rows: list[tuple[str, int, int]],
    title: str,
    labels: tuple[str, str] = ("Prijave", "Odjave"),
    width: int = 760,
    height: int = 220,
) -> Markup:
    """Two series per category (e.g. weekly signups vs unsubscribes)."""
    pad_left, pad_right, pad_top, pad_bottom = 40, 12, 14, 30
    inner_w = width - pad_left - pad_right
    inner_h = height - pad_top - pad_bottom
    max_value = _nice_max(max((max(a, b) for _, a, b in rows), default=0))
    n = max(1, len(rows))
    slot = inner_w / n
    bar_w = max(2.0, slot * 0.34)
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(title)}" preserveAspectRatio="none"><title>{escape(title)}</title>'
    ]
    parts += _y_axis(max_value, pad_left, width, pad_right, pad_top, inner_h)
    for index, (label, first, second) in enumerate(rows):
        base_x = pad_left + index * slot + slot * 0.14
        for offset, value, css, name in (
            (0, first, "chart-bar", labels[0]),
            (bar_w + 2, second, "chart-bar-alt", labels[1]),
        ):
            bar_h = inner_h * value / max_value if max_value else 0
            parts.append(
                f'<rect class="{css}" x="{base_x + offset:.1f}" '
                f'y="{pad_top + inner_h - bar_h:.1f}" width="{bar_w:.1f}" '
                f'height="{max(bar_h, 0.5):.1f}" rx="2"><title>{escape(label)} — '
                f"{escape(name)}: {value}</title></rect>"
            )
        if n <= 14 or index % 2 == 0:
            parts.append(
                f'<text class="chart-label" x="{base_x + bar_w:.1f}" y="{height - 10}" '
                f'text-anchor="middle">{escape(label)}</text>'
            )
    parts.append("</svg>")
    return Markup("".join(parts))
