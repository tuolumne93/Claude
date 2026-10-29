#!/usr/bin/env python3
"""Mine competitor reviews for unmet needs in children's tableware.

Input: a CSV of reviews. Columns are auto-detected (case-insensitive):
  text    : text | review | body | content | review_text      (required)
  title   : title | headline | summary
  rating  : rating | stars | score                            (1-5)
  product : product | product_name | item | asin | brand
  date    : date | review_date | created | submitted          (YYYY-MM-DD...)

Output (in --out): report.html, themes.json
  * which complaints are most common, most severe and most widespread across
    competitors (widespread = an unsolved category problem = opportunity)
  * a product x complaint matrix
  * verbatim "I wish..." feature requests
  * recurring negative phrases the theme list doesn't cover yet
  * complaint trend by quarter

Collect reviews in ways the source allows (your own store's exports,
purchased datasets, retailer APIs, or by hand). Don't scrape sites whose terms
forbid it.

Example
  python reviews/analyze_reviews.py reviews/sample_reviews.csv --out out/reviews
"""

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from tablekit.report import bar, esc, page, sparkline, table  # noqa: E402

COLUMNS = {
    "text": ["text", "review", "body", "content", "review_text", "comment"],
    "title": ["title", "headline", "summary", "review_title"],
    "rating": ["rating", "stars", "score", "star_rating"],
    "product": ["product", "product_name", "item", "asin", "brand", "sku"],
    "date": ["date", "review_date", "created", "submitted", "created_at"],
}

NEG_WORDS = re.compile(r"\b(disappoint\w*|terrible|awful|useless|returned|return(?:ing)?|broke|waste|"
                       r"worst|hate|annoying|frustrat\w*|doesn'?t work|poor)\b", re.I)

STOP = set("""a an the and or but if to of in on at for with is was are were be been it its it's this that
these those my our his her their them they we i you he she me us so too very just really not no
as from by up out than then there here when what which who will would can could do does did have
has had get got one all also about after again more most some any only because into over even
""".split())


def detect_columns(fieldnames):
    lower = {f.lower().strip(): f for f in fieldnames}
    found = {}
    for key, options in COLUMNS.items():
        for o in options:
            if o in lower:
                found[key] = lower[o]
                break
    if "text" not in found:
        raise SystemExit(f"no review text column found; columns are {fieldnames}")
    return found


def load_reviews(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(line for line in fh if not line.startswith("#"))]
    if not rows:
        raise SystemExit("no rows in CSV")
    cols = detect_columns(rows[0].keys())
    out = []
    for r in rows:
        text = (r.get(cols.get("title", ""), "") or "") + ". " + (r[cols["text"]] or "")
        rating = None
        if "rating" in cols:
            m = re.search(r"\d+(?:\.\d+)?", r[cols["rating"]] or "")
            rating = float(m.group()) if m else None
        out.append({
            "text": text.strip(". "),
            "rating": rating,
            "product": (r.get(cols.get("product", ""), "") or "unknown").strip() or "unknown",
            "date": (r.get(cols.get("date", ""), "") or "").strip(),
        })
    return out


def is_negative(review):
    if review["rating"] is not None:
        return review["rating"] <= 3
    return bool(NEG_WORDS.search(review["text"]))


def quarter(date):
    m = re.match(r"(\d{4})-(\d{1,2})", date)
    if not m:
        return None
    return f"{m.group(1)}-Q{(int(m.group(2)) - 1) // 3 + 1}"


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def highlight(sentence, regex):
    out, last = [], 0
    for m in regex.finditer(sentence):
        out.append(esc(sentence[last:m.start()]) + f"<mark>{esc(m.group())}</mark>")
        last = m.end()
    return "".join(out) + esc(sentence[last:])


def tokens(text):
    return [w for w in re.findall(r"[a-z']+", text.lower())]


def analyze(reviews, themes_cfg):
    themes = {k: (v["label"], re.compile("|".join(f"(?:{p})" for p in v["patterns"]), re.I))
              for k, v in themes_cfg["themes"].items()}
    wish_re = re.compile("|".join(f"(?:{p})" for p in themes_cfg["wish_patterns"]), re.I)

    products = sorted({r["product"] for r in reviews})
    n_by_product = Counter(r["product"] for r in reviews)
    negatives = [r for r in reviews if is_negative(r)]
    stats = {k: {"label": lab, "mentions": 0, "neg": 0, "ratings": [], "products": Counter(),
                 "quotes": [], "by_quarter": Counter()} for k, (lab, _) in themes.items()}
    wishes = []
    for r in reviews:
        neg = is_negative(r)
        r["themes"] = []
        for k, (_, rx) in themes.items():
            if not rx.search(r["text"]):
                continue
            r["themes"].append(k)
            st = stats[k]
            st["mentions"] += 1
            if r["rating"] is not None:
                st["ratings"].append(r["rating"])
            if neg:
                st["neg"] += 1
                st["products"][r["product"]] += 1
                q = quarter(r["date"])
                if q:
                    st["by_quarter"][q] += 1
                sent = next((s for s in sentences(r["text"]) if rx.search(s)), r["text"])
                st["quotes"].append((r["rating"] or 0, r["product"], highlight(sent, rx)))
        for m in wish_re.finditer(r["text"]):
            wish = m.group().strip()
            if len(wish) > 12:
                wishes.append({"wish": wish, "product": r["product"], "themes": list(r["themes"])})

    total_neg = max(1, len(negatives))
    results = []
    for k, st in stats.items():
        if not st["mentions"]:
            continue
        avg = sum(st["ratings"]) / len(st["ratings"]) if st["ratings"] else None
        severity = (5 - avg) / 4 if avg is not None else 0.5
        spread = len(st["products"]) / max(1, len(products))
        share = st["neg"] / total_neg
        results.append({
            "theme": k, "label": st["label"], "mentions": st["mentions"], "negative_mentions": st["neg"],
            "share_of_negative_reviews": share, "avg_rating_when_mentioned": avg,
            "products_affected": len(st["products"]), "spread": spread,
            "opportunity": share * severity * (0.5 + spread),
            "per_product_rate": {p: st["products"][p] / n_by_product[p] for p in products},
            "by_quarter": dict(sorted(st["by_quarter"].items())),
            "quotes": [q[2] for q in sorted(st["quotes"], key=lambda q: q[0])[:4]],
        })
    top = max((x["opportunity"] for x in results), default=1) or 1
    for x in results:
        x["opportunity_index"] = round(100 * x["opportunity"] / top)
    results.sort(key=lambda x: -x["opportunity"])

    # Phrases over-represented in negative reviews that no theme caught.
    neg_bi, pos_bi = Counter(), Counter()
    for r in reviews:
        toks = tokens(r["text"])
        grams = {f"{a} {b}" for a, b in zip(toks, toks[1:]) if not (a in STOP and b in STOP)}
        target = neg_bi if is_negative(r) and not r["themes"] else (pos_bi if not is_negative(r) else None)
        if target is not None:
            target.update(grams)
    n_neg, n_pos = sum(neg_bi.values()) + 1, sum(pos_bi.values()) + 1
    uncovered = sorted(
        ((g, c, math.log((c + 0.5) / n_neg) - math.log((pos_bi[g] + 0.5) / n_pos))
         for g, c in neg_bi.items() if c >= 2),
        key=lambda t: -t[2])[:15]

    return {"n_reviews": len(reviews), "n_negative": len(negatives), "products": products,
            "n_by_product": dict(n_by_product), "themes": results, "wishes": wishes,
            "uncovered_phrases": [{"phrase": g, "count": c} for g, c, _ in uncovered]}


def render(res):
    themes = res["themes"]
    parts = [f"<p>{res['n_reviews']} reviews across {len(res['products'])} products · "
             f"{res['n_negative']} negative (rating ≤ 3 or negative wording).</p>"]

    parts.append("<h2>Opportunity ranking</h2><p class='muted small'>Opportunity = how often a complaint "
                 "appears in negative reviews × how low those reviews score × how many competitors share it. "
                 "A complaint that every brand gets is an unsolved category problem, which is where a unique "
                 "product can win.</p>")
    rows = []
    for t in themes:
        if not t["negative_mentions"]:
            continue
        rows.append([t["label"], f"{bar(t['opportunity_index'] / 100)}<span class='small'>{t['opportunity_index']}</span>",
                     t["negative_mentions"], f"{t['share_of_negative_reviews']:.0%}",
                     "-" if t["avg_rating_when_mentioned"] is None else f"{t['avg_rating_when_mentioned']:.1f}★",
                     f"{t['products_affected']}/{len(res['products'])}"])
    parts.append(table(["Complaint", "Opportunity", "Negative mentions", "% of negative reviews",
                        "Avg rating", "Competitors affected"], rows, raw_cols=(1,)))

    parts.append("<h2>Who has which problem</h2><p class='muted small'>Share of each product's reviews "
                 "that complain about the theme.</p>")
    shown = [t for t in themes if t["negative_mentions"]][:10]
    mrows = []
    for p in res["products"]:
        cells = [f"{esc(p)} <span class='muted small'>({res['n_by_product'][p]})</span>"]
        for t in shown:
            v = t["per_product_rate"][p]
            alpha = min(1.0, v * 2.5)
            cells.append(f"<span style='display:block;padding:2px 4px;border-radius:4px;"
                         f"background:rgba(192,57,43,{alpha:.2f});color:{'#fff' if alpha > .5 else 'inherit'}'>"
                         f"{v:.0%}</span>" if v else "<span class='muted'>·</span>")
        mrows.append(cells)
    parts.append(table(["Product"] + [t["label"] for t in shown], mrows, raw_cols=tuple(range(len(shown) + 1))))

    parts.append("<h2>What customers say</h2>")
    for t in shown[:8]:
        quotes = "".join(f"<blockquote>{q}</blockquote>" for q in t["quotes"])
        parts.append(f"<div class='card'><h3>{esc(t['label'])}</h3>{quotes}</div>")

    parts.append("<h2>Feature requests (“I wish…”)</h2>")
    if res["wishes"]:
        wrows = [[w["wish"], w["product"], ", ".join(w["themes"]) or "-"] for w in res["wishes"]]
        parts.append(table(["Request", "Product", "Related themes"], wrows))
    else:
        parts.append("<p class='muted'>None found.</p>")

    parts.append("<h2>Uncovered negative phrases</h2><p class='muted small'>Phrases that recur in negative "
                 "reviews that no theme matched. Add them to themes.json if they're a real pattern.</p>")
    parts.append(", ".join(f"<span class='pill'>{esc(u['phrase'])} ×{u['count']}</span>"
                           for u in res["uncovered_phrases"]) or "<p class='muted'>None.</p>")

    quarters = sorted({q for t in themes for q in t["by_quarter"]})
    if len(quarters) >= 2:
        parts.append("<h2>Complaint trend by quarter</h2>")
        trows = [[t["label"], sparkline([[t["by_quarter"].get(q, 0) for q in quarters]]),
                  " → ".join(str(t["by_quarter"].get(q, 0)) for q in quarters)] for t in shown]
        parts.append(f"<p class='muted small'>{esc(quarters[0])} to {esc(quarters[-1])}</p>")
        parts.append(table(["Complaint", "Trend", "Counts"], trows, raw_cols=(1,)))
    return page("Competitor review insights", "".join(parts), "Children's tableware · review mining")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="reviews CSV")
    ap.add_argument("--themes", default=str(HERE / "themes.json"))
    ap.add_argument("--out", default="out/reviews")
    args = ap.parse_args()

    res = analyze(load_reviews(args.csv), json.loads(Path(args.themes).read_text()))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "themes.json").write_text(json.dumps(res, indent=2))
    (out / "report.html").write_text(render(res))
    print(f"{res['n_reviews']} reviews, {res['n_negative']} negative\n\nTop opportunities:")
    for t in res["themes"][:6]:
        print(f"  {t['opportunity_index']:>3}  {t['label']}  ({t['negative_mentions']} negative mentions, "
              f"{t['products_affected']}/{len(res['products'])} competitors)")
    print(f"\n{len(res['wishes'])} feature requests found\nwrote {out / 'report.html'}")


if __name__ == "__main__":
    main()
