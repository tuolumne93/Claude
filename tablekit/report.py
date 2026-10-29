"""Tiny HTML report builder shared by the tools (no dependencies)."""

import html

CSS = """
:root{--bg:#fbfaf7;--fg:#22211f;--muted:#6b6862;--line:#e4e0d8;--card:#fff;
--good:#2f7d4f;--warn:#b7791f;--bad:#c0392b;--accent:#3b6ea5}
@media (prefers-color-scheme: dark){:root{--bg:#1b1a19;--fg:#ecebe8;--muted:#a3a09a;
--line:#36342f;--card:#242321;--good:#5cc28a;--warn:#e0a84a;--bad:#ef6f5e;--accent:#7fb0e6}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.7rem;margin:.2em 0}h2{font-size:1.25rem;margin-top:2em;border-bottom:1px solid var(--line);padding-bottom:.3em}
h3{font-size:1.05rem;margin:1.2em 0 .4em}
.muted{color:var(--muted)}.small{font-size:.85rem}
table{border-collapse:collapse;width:100%;margin:.5em 0;font-size:.92rem}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted)}
.wrap{overflow-x:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.78rem;border:1px solid var(--line)}
.good{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden}
.bar>span{display:block;height:100%;background:var(--accent)}
.sw{height:64px;border-radius:8px;border:1px solid var(--line)}
.chip{display:inline-block;width:18px;height:18px;border-radius:4px;border:1px solid var(--line);vertical-align:middle}
blockquote{margin:.4em 0;padding:.3em .8em;border-left:3px solid var(--line);color:var(--muted)}
mark{background:#ffe9a8;color:#22211f;padding:0 2px;border-radius:2px}
.disclaimer{border-left:4px solid var(--warn);padding:10px 14px;background:var(--card)}
"""


def esc(x):
    return html.escape(str(x), quote=True)


def page(title, body, subtitle=""):
    sub = f'<p class="muted">{esc(subtitle)}</p>' if subtitle else ""
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}</style></head>"
            f"<body><main><h1>{esc(title)}</h1>{sub}{body}</main></body></html>")


def table(headers, rows, raw_cols=()):
    """rows: list of lists. Columns whose index is in raw_cols are inserted unescaped."""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = []
    for r in rows:
        cells = "".join(f"<td>{c if i in raw_cols else esc(c)}</td>" for i, c in enumerate(r))
        body.append(f"<tr>{cells}</tr>")
    return f"<div class='wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def bar(frac):
    pct = max(0.0, min(1.0, frac)) * 100
    return f"<div class='bar'><span style='width:{pct:.1f}%'></span></div>"


def sparkline(series, width=160, height=36, colors=("var(--accent)", "var(--warn)")):
    """series: list of lists of numbers (same length). Returns inline SVG."""
    vals = [v for s in series for v in s if v is not None]
    if not vals:
        return ""
    lo, hi = 0.0, max(vals) or 1.0
    n = max(len(s) for s in series)
    parts = []
    for s, col in zip(series, colors):
        pts = []
        for i, v in enumerate(s):
            if v is None:
                continue
            x = 2 + (width - 4) * (i / max(1, n - 1))
            y = height - 2 - (height - 4) * ((v - lo) / (hi - lo))
            pts.append(f"{x:.1f},{y:.1f}")
        parts.append(f"<polyline fill='none' stroke='{col}' stroke-width='2' points='{' '.join(pts)}'/>")
    return (f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' "
            f"role='img' aria-label='trend'>{''.join(parts)}</svg>")
