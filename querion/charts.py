"""Colored chart rendering for Querion.

The analyst emits a chart spec (JSON); we render a bar / line / pie chart with
matplotlib (headless Agg) to a PNG, or fall back to a unicode bar chart that
needs no image support at all. Built to never become unreadable: a spec with
many series is capped to the top N by total and the rest folded into a grey
"Other (N more)", the legend sits outside the plot, and value labels are only
drawn where they cannot collide.
"""

import os
import tempfile

PALETTE = [
    "#4E79E6", "#10B981", "#F59E0B", "#EC4899",
    "#8B5CF6", "#14B8A6", "#EF4444", "#64748B",
]
OTHER_COLOR = "#94A3B8"
MAX_SERIES = 8
INK = "#1A1D27"
PANEL = "#FAFBFD"


class ChartError(RuntimeError):
    pass


def text_chart(spec: dict) -> str:
    series = spec.get("series") or []
    x = spec.get("x") or []
    if not series or not x:
        return ""
    vals = list(series[0].get("values") or [])
    pairs = [(str(lbl), v) for lbl, v in zip(x, vals)]
    nums = [v for _, v in pairs if isinstance(v, (int, float))]
    mx = max(nums) if nums else 0
    width = 22
    lwidth = min(max((len(l) for l, _ in pairs), default=4), 14)
    out = [spec.get("title") or "chart", ""]
    for label, v in pairs:
        if isinstance(v, (int, float)):
            n = int(round((v / mx) * width)) if mx else 0
            out.append(f"{label[:lwidth]:<{lwidth}}  {'#' * max(n, 0):<{width}}  {v:,.0f}")
        else:
            out.append(f"{label[:lwidth]:<{lwidth}}  {v}")
    return "```\n" + "\n".join(out) + "\n```"


def _color(series: dict, i: int) -> str:
    return series.get("color") or PALETTE[i % len(PALETTE)]


def _cap_series(series: list, max_keep: int = MAX_SERIES):
    if len(series) <= max_keep:
        return series, 0
    total = lambda s: sum(v for v in (s.get("values") or []) if isinstance(v, (int, float)))
    ranked = sorted(series, key=total, reverse=True)
    kept, rest = ranked[: max_keep - 1], ranked[max_keep - 1:]
    width = max((len(s.get("values") or []) for s in rest), default=0)
    other = []
    for i in range(width):
        other.append(sum(
            (s.get("values") or [])[i]
            for s in rest
            if i < len(s.get("values") or []) and isinstance((s.get("values") or [])[i], (int, float))
        ))
    kept = list(kept) + [{"name": f"Other ({len(rest)} more)", "values": other, "color": OTHER_COLOR}]
    return kept, len(rest)


def render(spec: dict) -> str:
    """Render a chart spec to a PNG file; return its path. Raises ChartError."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except ImportError as exc:
        raise ChartError("matplotlib is not installed") from exc

    ctype = (spec.get("type") or "bar").lower()
    title = spec.get("title") or ""
    x = spec.get("x") or []
    series = spec.get("series") or []
    if not series or (not x and ctype != "pie"):
        raise ChartError("chart needs x and at least one series")

    labels = [str(v) for v in x]
    thousands = FuncFormatter(lambda v, _: f"{v:,.0f}")

    if ctype == "pie":
        fig, ax = plt.subplots(figsize=(8.8, 4.6), dpi=130)
        vals = [(str(l), v) for l, v in zip(labels, series[0].get("values") or [])
                if isinstance(v, (int, float)) and v > 0]
        if not vals:
            raise ChartError("pie needs positive values")
        vals.sort(key=lambda p: p[1], reverse=True)
        if len(vals) > 7:
            head, tail = vals[:6], vals[6:]
            vals = head + [(f"Other ({len(tail)} more)", sum(v for _, v in tail))]
        names = [n for n, _ in vals]
        sizes = [v for _, v in vals]
        tot = sum(sizes) or 1
        wedges, _, _ = ax.pie(
            sizes, labels=None, colors=[PALETTE[i % len(PALETTE)] for i in range(len(sizes))],
            autopct=lambda p: f"{p:.1f}%" if p >= 4 else "", pctdistance=0.78,
            startangle=90, counterclock=False,
            wedgeprops={"width": 0.42, "linewidth": 1.5, "edgecolor": "white"},
            textprops={"fontsize": 9.5, "fontweight": "bold", "color": "white"})
        ax.axis("equal")
        ax.legend(wedges, [f"{n}   {v / tot * 100:.1f}%" for n, v in vals],
                  loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=10)
        ax.set_title(title, fontsize=14, fontweight="bold", loc="left", pad=12, color=INK)
        return _save(fig, plt)

    series, _ = _cap_series(series)
    n = len(series)
    multi = n > 1 or bool(series[0].get("name"))
    fig, ax = plt.subplots(figsize=(9.6, 4.8) if multi else (8.4, 4.6), dpi=130)
    fig.patch.set_facecolor("white")
    ax.set_facecolor(PANEL)

    if ctype == "line":
        ax.margins(x=0.03)
        lw, ms = (2.4, 5) if n <= 4 else (1.8, 3.5)
        for i, s in enumerate(series):
            v = s.get("values", [])
            ax.plot(labels, v, marker="o", markersize=ms, linewidth=lw,
                    color=_color(s, i), label=s.get("name", ""))
            if n == 1 and v and isinstance(v[-1], (int, float)):
                ax.annotate(f"{v[-1]:,.0f}", (len(labels) - 1, v[-1]),
                            textcoords="offset points", xytext=(8, 5),
                            fontsize=9, color=_color(s, i), fontweight="bold")
        ax.yaxis.set_major_formatter(thousands)
    else:
        width = 0.8 / max(n, 1)
        idx = range(len(labels))
        for i, s in enumerate(series):
            offs = [j + (i - (n - 1) / 2) * width for j in idx]
            bars = ax.bar(offs, s.get("values", []), width=width,
                          color=_color(s, i), label=s.get("name", ""))
            if n <= 3 and len(labels) * n <= 18:
                ax.bar_label(bars, fmt=lambda v: f"{v:,.0f}", fontsize=8.5, padding=3, color=INK)
        ax.set_xticks(list(idx))
        ax.set_xticklabels(labels)
        ax.yaxis.set_major_formatter(thousands)

    ax.grid(True, axis="y", alpha=0.3, linestyle="--")
    ax.set_axisbelow(True)
    ax.set_title(title, fontsize=14, fontweight="bold", loc="left", pad=12, color=INK)
    if multi:
        ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False,
                  fontsize=9, ncol=2 if n > 9 else 1)
    ax.spines[["top", "right"]].set_visible(False)
    if len(labels) > 6:
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8.5)
    return _save(fig, plt)


def _save(fig, plt) -> str:
    fd, path = tempfile.mkstemp(prefix="querion_chart_", suffix=".png")
    os.close(fd)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path
