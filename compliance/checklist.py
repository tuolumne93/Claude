#!/usr/bin/env python3
"""Generate a compliance & claims checklist for a children's tableware product.

Example
  python compliance/checklist.py --name "Scoop plate" --product plate \\
      --materials silicone,pp --min-age-months 6 --markets US,EU,UK \\
      --features suction,printed_decoration,dishwasher_claim \\
      --claims "BPA-free, eco-friendly, dishwasher safe, pediatrician recommended"

  python compliance/checklist.py --list      # show valid options

Output: an interactive HTML checklist (tick boxes and notes are saved in your
browser) and a Markdown copy for tickets/specs.

NOT LEGAL ADVICE. The rules file is a starting point that was last reviewed on
the date in rules.json. Confirm everything with an accredited lab or a
compliance consultant for each market.
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from tablekit.report import esc, page  # noqa: E402

PRODUCTS = ["plate", "bowl", "cup", "cutlery", "snack_cup", "food_container", "placemat"]
FEATURES = ["suction", "lid", "spout_valve", "straw", "printed_decoration", "coating", "electronics_battery",
            "heat_retaining", "microwave_use", "dishwasher_claim", "removable_parts"]
MARKETS = ["US", "EU", "UK", "CA", "AU"]
PRIORITY_ORDER = {"must": 0, "should": 1, "watch": 2}


def load():
    return json.loads((HERE / "rules.json").read_text()), json.loads((HERE / "claims.json").read_text())


def all_materials(kb):
    mats = set()
    for members in kb["material_groups"].values():
        mats.update(members)
    return sorted(mats)


def expand(materials, groups):
    """Return the selected materials plus every group name they belong to."""
    out = set(materials)
    for g, members in groups.items():
        if out & set(members):
            out.add(g)
    return out


def applies(rule, spec, groups):
    a = rule.get("applies", {})
    if rule["market"] != "ALL" and rule["market"] not in spec["markets"]:
        return False
    if "products" in a and spec["product"] not in a["products"]:
        return False
    if "materials" in a and not (set(a["materials"]) & expand(spec["materials"], groups)):
        return False
    if "features" in a and not (set(a["features"]) & set(spec["features"])):
        return False
    if "max_age_months" in a and spec["min_age_months"] >= a["max_age_months"]:
        return False
    return True


def check_claims(text, claims_kb):
    hits = []
    for c in claims_kb["claims"]:
        m = re.search(c["pattern"], text, re.I)
        if m:
            hits.append({**c, "matched": m.group()})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(hits, key=lambda h: order[h["risk"]])


def material_flags(spec):
    flags = []
    mats = set(spec["materials"])
    if "bamboo_composite" in mats:
        flags.append("Bamboo/plant-fibre plastic composite: not authorised in the EU/UK and usually melamine-based. "
                     "This is a high-risk material choice in every market.")
    if mats & {"melamine", "bamboo_composite"} and "microwave_use" in spec["features"]:
        flags.append("Melamine (incl. bamboo-melamine) + microwave use: FDA advises against microwaving melamine. "
                     "Remove the feature or the material.")
    if "stainless_steel" in mats and "microwave_use" in spec["features"]:
        flags.append("Metal parts and microwave use are incompatible.")
    if spec["min_age_months"] < 36 and spec["product"] == "cutlery" and "stainless_steel" in mats:
        flags.append("Metal cutlery for under-3s: check sharp-edge/point tests and consider silicone-tipped designs.")
    if "spout_valve" in spec["features"] and spec["min_age_months"] < 36:
        flags.append("Valves/spouts for under-3s are frequent bite-through and mould complaints. Plan bite and "
                     "tensile tests, and make the valve removable for cleaning.")
    return flags


def build(spec):
    kb, claims_kb = load()
    rules = [r for r in kb["rules"] if applies(r, spec, kb["material_groups"])]
    rules.sort(key=lambda r: (r["market"] == "ALL", r["market"], PRIORITY_ORDER[r["priority"]], r["category"]))
    claims = check_claims(spec["claims"], claims_kb) if spec["claims"] else []
    return {"spec": spec, "last_reviewed": kb["last_reviewed"], "rules": rules,
            "claims": claims, "flags": material_flags(spec)}


def to_markdown(res):
    s = res["spec"]
    lines = [f"# Compliance checklist - {s['name']}", "",
             f"Product: {s['product']} · Materials: {', '.join(s['materials'])} · Youngest user: {s['min_age_months']} months  ",
             f"Markets: {', '.join(s['markets'])} · Features: {', '.join(s['features']) or 'none'}  ",
             f"Knowledge base last reviewed: {res['last_reviewed']}. Not legal advice: verify with an accredited lab.", ""]
    if res["flags"]:
        lines += ["## ⚠ Design red flags", ""] + [f"- {f}" for f in res["flags"]] + [""]
    market = None
    for r in res["rules"]:
        if r["market"] != market:
            market = r["market"]
            lines += [f"## {'All markets - performance & claims' if market == 'ALL' else market}", ""]
        lines.append(f"- [ ] **{r['title']}** ({r['priority']}, {r['category']}) - {r['requirement']}  ")
        lines.append(f"  Evidence: {r['evidence']}  Ref: {r['reference']}")
    if res["claims"]:
        lines += ["", "## Marketing claims review", ""]
        for c in res["claims"]:
            lines.append(f"- **\"{c['matched']}\"**: {c['risk']} risk. {c['advice']}")
    return "\n".join(lines) + "\n"


def to_html(res):
    s = res["spec"]
    key = "chk-" + re.sub(r"\W+", "-", s["name"].lower())
    parts = [f"<p>{esc(s['product'])} · {esc(', '.join(s['materials']))} · from {s['min_age_months']} months · "
             f"markets {esc(', '.join(s['markets']))} · features {esc(', '.join(s['features']) or 'none')}</p>",
             f"<p class='disclaimer small'>Starting-point checklist, not legal advice. Knowledge base last "
             f"reviewed {esc(res['last_reviewed'])}; regulations change. Confirm every item with an accredited "
             f"test lab or compliance consultant before launch.</p>",
             "<p><b id='progress'></b></p>"]
    if res["flags"]:
        parts.append("<h2 class='bad'>Design red flags</h2>" +
                     "".join(f"<div class='card bad'>{esc(f)}</div>" for f in res["flags"]))
    market = None
    for r in res["rules"]:
        if r["market"] != market:
            market = r["market"]
            parts.append(f"<h2>{'All markets: performance & claims' if market == 'ALL' else esc(market)}</h2>")
        pr = {"must": "bad", "should": "warn", "watch": "muted"}[r["priority"]]
        parts.append(
            f"<div class='card'><label style='display:flex;gap:10px;align-items:flex-start'>"
            f"<input type='checkbox' data-id='{esc(r['id'])}' style='margin-top:5px;transform:scale(1.3)'>"
            f"<span><b>{esc(r['title'])}</b> <span class='pill {pr}'>{esc(r['priority'])}</span> "
            f"<span class='pill'>{esc(r['category'])}</span><br>{esc(r['requirement'])}"
            f"<br><span class='small muted'><b>Evidence:</b> {esc(r['evidence'])}<br><b>Ref:</b> {esc(r['reference'])}</span>"
            f"</span></label><textarea data-note='{esc(r['id'])}' placeholder='Notes / lab / report no.' "
            f"style='width:100%;margin-top:8px;min-height:2.2em;font:inherit;background:transparent;color:inherit;"
            f"border:1px solid var(--line);border-radius:6px;padding:4px 8px'></textarea></div>")
    if s["claims"]:
        parts.append("<h2>Marketing claims review</h2>")
        if not res["claims"]:
            parts.append("<p class='good'>No risky claim wording detected.</p>")
        for c in res["claims"]:
            cls = {"high": "bad", "medium": "warn", "low": "muted"}[c["risk"]]
            parts.append(f"<div class='card'><b>“{esc(c['matched'])}”</b> <span class='pill {cls}'>{esc(c['risk'])} risk</span>"
                         f"<br>{esc(c['advice'])}</div>")
    script = f"""<script>
const K={json.dumps(key)};let st={{}};try{{st=JSON.parse(localStorage.getItem(K)||'{{}}')}}catch(e){{}}
const save=()=>{{try{{localStorage.setItem(K,JSON.stringify(st))}}catch(e){{}}}};
const boxes=[...document.querySelectorAll('[data-id]')];
const upd=()=>{{const n=boxes.filter(b=>b.checked).length;document.getElementById('progress').textContent=n+' / '+boxes.length+' items done'}};
boxes.forEach(b=>{{b.checked=!!st[b.dataset.id];b.onchange=()=>{{st[b.dataset.id]=b.checked;save();upd()}}}});
document.querySelectorAll('[data-note]').forEach(t=>{{t.value=st['n:'+t.dataset.note]||'';t.oninput=()=>{{st['n:'+t.dataset.note]=t.value;save()}}}});
upd();</script>"""
    return page(f"Compliance checklist: {s['name']}", "".join(parts) + script)


def csv_list(v):
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="New product")
    ap.add_argument("--product", default="plate", choices=PRODUCTS)
    ap.add_argument("--materials", default="silicone", help="comma list; see --list")
    ap.add_argument("--min-age-months", type=int, default=6, help="youngest intended user")
    ap.add_argument("--markets", default="US,EU", help="comma list of " + ",".join(MARKETS))
    ap.add_argument("--features", default="", help="comma list; see --list")
    ap.add_argument("--claims", default="", help="marketing claims / copy text to review")
    ap.add_argument("--claims-file", help="file with packaging or listing copy to review")
    ap.add_argument("--out", default="out/compliance")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    kb, _ = load()
    if args.list:
        print("products :", ", ".join(PRODUCTS))
        print("materials:", ", ".join(all_materials(kb)))
        print("features :", ", ".join(FEATURES))
        print("markets  :", ", ".join(MARKETS))
        return

    spec = {"name": args.name, "product": args.product, "materials": csv_list(args.materials.lower()),
            "min_age_months": args.min_age_months, "markets": [m.upper() for m in csv_list(args.markets)],
            "features": csv_list(args.features.lower()), "claims": args.claims}
    if args.claims_file:
        spec["claims"] += "\n" + Path(args.claims_file).read_text()
    for m in spec["materials"]:
        if m not in all_materials(kb):
            raise SystemExit(f"unknown material {m!r}; try --list")
    for f in spec["features"]:
        if f not in FEATURES:
            raise SystemExit(f"unknown feature {f!r}; try --list")
    for m in spec["markets"]:
        if m not in MARKETS:
            raise SystemExit(f"unknown market {m!r}; choose from {MARKETS}")

    res = build(spec)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"\W+", "_", args.name.lower()).strip("_")
    (out / f"{slug}.md").write_text(to_markdown(res))
    (out / f"{slug}.html").write_text(to_html(res))
    must = sum(r["priority"] == "must" for r in res["rules"])
    print(f"{len(res['rules'])} checklist items ({must} must) · {len(res['claims'])} claims flagged · "
          f"{len(res['flags'])} design red flags")
    for f in res["flags"]:
        print("  ! " + f)
    for c in res["claims"]:
        print(f"  claim '{c['matched']}': {c['risk']} risk")
    print(f"wrote {out / (slug + '.html')} and .md")


if __name__ == "__main__":
    main()
