#!/usr/bin/env python3
"""Forecast colour trends for children's products about a year ahead, and build
a product palette that also works on the table.

How it works
  1. You log colour "signals": one row per colour seen, with a date and a source
     type (forecast agency, adult fashion, interiors, kidswear, competitor
     launches, best-sellers, your own sales ...). extract_colors.py can pull
     colours straight from photos.
  2. Signals are grouped into colour families (CIEDE2000 distance).
  3. For each family the tool measures its share and momentum in
     leading sources (where colours appear first), bridge sources (kids fashion
     and nursery) and the market (children's tableware/feeding products today).
  4. Colours strong upstream but not yet common in the kids market are
     "whitespace". The 12-month projection = current market share + damped
     market momentum + part of the whitespace closing (--adoption).
  5. It recommends a launch palette (hero + supporting + neutral) and checks
     each colour for food camouflage, colour-blind distinguishability and,
     optionally, the nearest colour in your supplier's masterbatch/pigment library.

The forecast is only as good as the signals you feed it. Log consistently
(similar effort per source every quarter) and include at least 4-6 quarters.

Signals CSV columns: date (YYYY-MM-DD), hex, source_type, source_name, weight (optional), notes (optional)

Example
  python palette/trendcast.py palette/sample_signals.csv --out out/palette
  python palette/trendcast.py signals.csv --library supplier_colours.csv --horizon 4
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from tablekit.colorsci import (color_name, delta_e2000, hex_to_lab, lab_to_hex,  # noqa: E402
                               lab_to_lch, simulate_cvd)
from tablekit.report import esc, page, sparkline, table  # noqa: E402

SOURCES = json.loads((HERE / "sources.json").read_text())["source_types"]
FOODS = json.loads((HERE / "food_colors.json").read_text())["foods"]


# --- loading -------------------------------------------------------------------

def quarter_of(date):
    m = re.match(r"(\d{4})-(\d{1,2})", date.strip())
    if not m:
        raise ValueError(f"bad date {date!r} (use YYYY-MM-DD)")
    return int(m.group(1)) * 4 + (int(m.group(2)) - 1) // 3


def qlabel(q):
    return f"{q // 4}-Q{q % 4 + 1}"


def load_signals(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(line for line in fh if line.strip() and not line.startswith("#")):
            st = r["source_type"].strip()
            if st not in SOURCES:
                raise SystemExit(f"unknown source_type {st!r}; edit palette/sources.json or use one of {list(SOURCES)}")
            w = float(r.get("weight") or 1.0) * SOURCES[st]["weight"]
            rows.append({"q": quarter_of(r["date"]), "hex": r["hex"].strip(), "lab": hex_to_lab(r["hex"]),
                         "role": SOURCES[st]["role"], "w": w})
    if not rows:
        raise SystemExit("no signals")
    return rows


# --- clustering ----------------------------------------------------------------

def cluster(rows, threshold):
    """Greedy CIEDE2000 clustering + a few reassignment passes."""
    centroids = []
    for r in sorted(rows, key=lambda r: -r["w"]):
        if not any(delta_e2000(r["lab"], c) < threshold for c in centroids):
            centroids.append(r["lab"])
    for _ in range(4):
        groups = defaultdict(list)
        for r in rows:
            i = min(range(len(centroids)), key=lambda i: delta_e2000(r["lab"], centroids[i]))
            r["c"] = i
            groups[i].append(r)
        centroids = [tuple(sum(r["lab"][k] * r["w"] for r in g) / sum(r["w"] for r in g) for k in range(3))
                     for _, g in sorted(groups.items())]
        # merge centroids that drifted together
        merged = []
        for c in centroids:
            if not any(delta_e2000(c, m) < threshold / 2 for m in merged):
                merged.append(c)
        centroids = merged
    for r in rows:
        r["c"] = min(range(len(centroids)), key=lambda i: delta_e2000(r["lab"], centroids[i]))
    return centroids


# --- trend metrics ---------------------------------------------------------------

def slope(ys):
    pts = [(i, y) for i, y in enumerate(ys) if y is not None]
    if len(pts) < 2:
        return 0.0
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    den = sum((x - mx) ** 2 for x, _ in pts)
    return sum((x - mx) * (y - my) for x, y in pts) / den if den else 0.0


def recent(ys, n=2):
    vals = [y for y in ys[-n:] if y is not None]
    return sum(vals) / len(vals) if vals else 0.0


def metrics(rows, centroids, horizon, adoption, window):
    quarters = list(range(min(r["q"] for r in rows), max(r["q"] for r in rows) + 1))
    tot = defaultdict(float)
    by = defaultdict(float)
    for r in rows:
        tot[(r["role"], r["q"])] += r["w"]
        by[(r["c"], r["role"], r["q"])] += r["w"]

    def series(c, role):
        return [by[(c, role, q)] / tot[(role, q)] if tot[(role, q)] else None for q in quarters]

    has_bridge = any(r["role"] == "bridge" for r in rows)
    has_market = any(r["role"] == "market" for r in rows)
    out = []
    for c, lab in enumerate(centroids):
        lead, bridge, market = series(c, "leading"), series(c, "bridge"), series(c, "market")
        if has_bridge:
            pipe = [None if (a is None and b is None) else 0.6 * (a or 0) + 0.4 * (b or 0)
                    for a, b in zip(lead, bridge)]
        else:
            pipe = lead
        pipe_now, mkt_now = recent(pipe), recent(market)
        pipe_mom, mkt_mom = slope(pipe[-window:]), slope(market[-window:])
        whitespace = pipe_now - mkt_now if has_market else 0.0
        projected = max(0.0, mkt_now + 0.5 * horizon * mkt_mom + adoption * whitespace) if has_market \
            else max(0.0, pipe_now + 0.5 * horizon * pipe_mom)

        if pipe_mom < -0.004 and whitespace <= 0 or mkt_mom < -0.006:
            stage = "Declining"
        elif mkt_now < 0.05 and (pipe_now >= 0.05 or pipe_mom > 0.004) and whitespace > 0:
            stage = "Emerging"
        elif mkt_mom > 0.004 or whitespace > 0.03:
            stage = "Rising"
        elif mkt_now >= 0.10 and whitespace <= 0.01:
            stage = "Peak"
        else:
            stage = "Stable"

        hx = lab_to_hex(lab)
        L, C, h = lab_to_lch(lab)
        out.append({"hex": hx, "name": color_name(hx), "lab": [round(v, 1) for v in lab], "chroma": C,
                    "stage": stage, "pipeline_share": pipe_now, "market_share": mkt_now,
                    "pipeline_momentum": pipe_mom, "market_momentum": mkt_mom, "whitespace": whitespace,
                    "projected_share": projected, "signals": sum(1 for r in rows if r["c"] == c),
                    "series": {"pipeline": pipe, "market": market}})
    out.sort(key=lambda x: -x["projected_share"])
    return [qlabel(q) for q in quarters], out


# --- palette building & checks -----------------------------------------------------

def food_check(hx):
    lab = hex_to_lab(hx)
    d = sorted(((delta_e2000(lab, hex_to_lab(fh)), food) for food, fh in FOODS.items()))
    return {"min_delta_e": round(d[0][0], 1), "camouflages": [f for de, f in d if de < 15]}


def cvd_check(hexes):
    issues = []
    for kind in ("protanopia", "deuteranopia", "tritanopia"):
        sim = {h: hex_to_lab(simulate_cvd(h, kind)) for h in hexes}
        for i, a in enumerate(hexes):
            for b in hexes[i + 1:]:
                de = delta_e2000(sim[a], sim[b])
                if de < 10:
                    issues.append({"a": a, "b": b, "type": kind, "delta_e": round(de, 1)})
    return issues


def nearest(hx, library):
    lab = hex_to_lab(hx)
    best = min(library, key=lambda e: delta_e2000(lab, e["lab"]))
    return best["name"], best["hex"], round(delta_e2000(lab, best["lab"]), 1)


def build_palette(clusters, size):
    chosen = []

    def distinct(c, min_de=15):
        return all(delta_e2000(hex_to_lab(c["hex"]), hex_to_lab(x["hex"])) >= min_de for x in chosen)

    colourful = [c for c in clusters if c["chroma"] >= 10 and c["stage"] != "Declining"]
    rank = {"Emerging": 0, "Rising": 1}
    pref = sorted(colourful, key=lambda c: rank.get(c["stage"], 2))  # stable sort keeps projection order
    for c in pref:
        if len(chosen) >= size - 1:
            break
        if distinct(c):
            chosen.append(dict(c, role="hero" if not chosen else "supporting"))
    neutrals = [c for c in clusters if c["chroma"] < 10 and c["stage"] != "Declining"]
    neutral = neutrals[0] if neutrals else {"hex": "#EDE6DA", "name": "oatmeal", "stage": "fallback",
                                            "projected_share": 0, "market_share": 0}
    chosen.append(dict(neutral, role="neutral"))
    return chosen


# --- report ------------------------------------------------------------------------

STAGE_CLASS = {"Emerging": "good", "Rising": "good", "Peak": "warn", "Stable": "muted", "Declining": "bad"}


def chip(hx, size=18):
    return f"<span class='chip' style='background:{hx};width:{size}px;height:{size}px'></span>"


def render(quarters, clusters, palette, cvd, library, horizon, has_market):
    pct = lambda v: f"{v * 100:.1f}%"  # noqa: E731
    pp = lambda v: f"{v * 100:+.1f}pp"  # noqa: E731
    parts = [f"<p>{len(clusters)} colour families from {sum(c['signals'] for c in clusters)} signals, "
             f"{esc(quarters[0])} to {esc(quarters[-1])}. Projection horizon: {horizon} quarters.</p>"]

    parts.append("<h2>Recommended launch palette</h2><div class='grid'>")
    for p in palette:
        fc = food_check(p["hex"])
        lib = ""
        if library:
            n, lh, de = nearest(p["hex"], library)
            q = "good" if de < 2 else ("warn" if de < 5 else "bad")
            lib = (f"<div class='small'>Library: {chip(lh, 12)} {esc(n)} "
                   f"<span class='{q}'>ΔE {de}</span></div>")
        food = (f"<span class='good'>OK on food (min ΔE {fc['min_delta_e']})</span>" if not fc["camouflages"]
                else f"<span class='warn'>Blends with: {esc(', '.join(fc['camouflages']))}</span>")
        parts.append(f"<div class='card'><div class='sw' style='background:{p['hex']}'></div>"
                     f"<b>{esc(p['name'])}</b> <span class='pill'>{esc(p['role'])}</span><br>"
                     f"<span class='small muted'>{esc(p['hex'])} · {esc(p['stage'])}</span>"
                     f"<div class='small'>{food}</div>{lib}</div>")
    parts.append("</div>")
    if cvd:
        parts.append("<p class='warn small'>Colour-blind check: " + "; ".join(
            f"{chip(i['a'], 12)} vs {chip(i['b'], 12)} look alike with {esc(i['type'])} (ΔE {i['delta_e']})"
            for i in cvd) + ". Avoid using that pair alone to distinguish sections or sizes.</p>")
    else:
        parts.append("<p class='good small'>Colour-blind check: every palette pair stays distinguishable "
                     "under protanopia, deuteranopia and tritanopia simulation.</p>")

    parts.append("<h2>All colour families</h2><p class='muted small'>Pipeline = leading + bridge sources "
                 "(where colours show up first). Market = children's tableware today. Whitespace = pipeline − "
                 "market. Trend line: blue = pipeline, amber = market.</p>")
    rows = []
    for c in clusters:
        rows.append([f"{chip(c['hex'], 28)}", f"<b>{esc(c['name'])}</b><br><span class='small muted'>{esc(c['hex'])}</span>",
                     f"<span class='pill {STAGE_CLASS[c['stage']]}'>{esc(c['stage'])}</span>",
                     pct(c["market_share"]) if has_market else "-", pct(c["pipeline_share"]),
                     pp(c["whitespace"]) if has_market else "-",
                     pp(c["market_momentum"] if has_market else c["pipeline_momentum"]) + "/q",
                     f"<b>{pct(c['projected_share'])}</b>",
                     sparkline([c["series"]["pipeline"], c["series"]["market"]], width=140, height=32),
                     c["signals"]])
    parts.append(table(["", "Colour", "Stage", "Market now", "Pipeline now", "Whitespace", "Momentum",
                        f"Projected +{horizon}q", "Trend", "Signals"], rows, raw_cols=(0, 1, 2, 7, 8)))
    parts.append("<h2>How to read this</h2><ul class='small'>"
                 "<li><b>Emerging</b>: strong or growing upstream, still rare in kids' tableware. This is first-mover "
                 "territory and the best fit for a hero colourway launching in about 12 months.</li>"
                 "<li><b>Rising</b>: already growing in the market. Lower risk, but less unique.</li>"
                 "<li><b>Peak</b>: widely used, with no upstream growth. Fine for core SKUs, not for news.</li>"
                 "<li><b>Declining</b>: losing share upstream or in market. Avoid for new launches.</li>"
                 "<li>The table is sorted by projected share, which shows how common a colour will be, not how fresh. "
                 "A declining colour can still have a large share. Use the stage to pick launch colours.</li>"
                 "<li>Food check flags colours with CIEDE2000 &lt; 15 to common toddler foods, where food may be hard to "
                 "see on the plate. Colour-blind check flags palette pairs with ΔE &lt; 10 under simulation.</li></ul>")
    return page("Colour trend forecast", "".join(parts), "Children's tableware · signal-based colour forecasting")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("signals", help="signals CSV")
    ap.add_argument("--out", default="out/palette")
    ap.add_argument("--horizon", type=int, default=4, help="quarters ahead to project (4 = 12 months)")
    ap.add_argument("--adoption", type=float, default=0.5,
                    help="share of the upstream/market gap expected to close over the horizon (0-1)")
    ap.add_argument("--threshold", type=float, default=12, help="CIEDE2000 distance that splits colour families")
    ap.add_argument("--window", type=int, default=6, help="quarters used for momentum")
    ap.add_argument("--palette-size", type=int, default=5)
    ap.add_argument("--library", help="CSV name,hex of colours your supplier can make (masterbatch / pigment library)")
    args = ap.parse_args()

    rows = load_signals(args.signals)
    centroids = cluster(rows, args.threshold)
    quarters, clusters = metrics(rows, centroids, args.horizon, args.adoption, args.window)
    palette = build_palette(clusters, args.palette_size)
    cvd = cvd_check([p["hex"] for p in palette])
    library = None
    if args.library:
        with open(args.library, newline="", encoding="utf-8-sig") as fh:
            library = [{"name": r["name"], "hex": r["hex"], "lab": hex_to_lab(r["hex"])} for r in csv.DictReader(fh)]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    has_market = any(r["role"] == "market" for r in rows)
    (out / "forecast.html").write_text(render(quarters, clusters, palette, cvd, library, args.horizon, has_market))
    (out / "forecast.json").write_text(json.dumps({
        "quarters": quarters, "clusters": clusters,
        "palette": [{**p, "food_check": food_check(p["hex"])} for p in palette], "cvd_issues": cvd}, indent=2))

    print(f"{len(clusters)} colour families · data {quarters[0]} to {quarters[-1]}\n")
    print(f"{'colour':24} {'hex':8} {'stage':10} {'market':>7} {'pipeline':>8} {'proj+' + str(args.horizon) + 'q':>8}")
    for c in clusters[:12]:
        print(f"{c['name'][:24]:24} {c['hex']:8} {c['stage']:10} {c['market_share'] * 100:6.1f}% "
              f"{c['pipeline_share'] * 100:7.1f}% {c['projected_share'] * 100:7.1f}%")
    print("\nLaunch palette: " + ", ".join(f"{p['name']} {p['hex']} ({p['role']})" for p in palette))
    print(f"wrote {out / 'forecast.html'}")


if __name__ == "__main__":
    main()
