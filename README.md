# Children's tableware development toolkit

Four tools for developing children's tableware:

| Tool | What it does | Run |
|---|---|---|
| **Parametric CAD** (`cad/`) | Plate, bowl, cup, spoon and suction cup models driven by age-group presets. It exports STLs and reports capacity, mass, tip-over angle and a small-parts screen. | `python cad/build.py --age all --product all` |
| **Review analyser** (`reviews/`) | Ranks competitor complaints by frequency, severity and how many brands share them, and extracts "I wish…" feature requests. | `python reviews/analyze_reviews.py reviews/sample_reviews.csv` |
| **Compliance checklist** (`compliance/`) | Builds a market × material × age checklist (US, EU, UK, CA, AU), flags risky materials and reviews marketing claims. | `python compliance/checklist.py --list` |
| **Colour trend forecaster** (`palette/`) | Projects which colours will be emerging in children's products about 12 months ahead and builds a launch palette, with food-contrast, colour-blind and supplier-match checks. | `python palette/trendcast.py palette/sample_signals.csv` |

Every tool writes an HTML report (light/dark mode, works on phones) to `out/…` that you can open in a browser.

**Requirements:** Python 3.9+, `numpy` and `Pillow` (`pip install -r requirements.txt`), and
[OpenSCAD](https://openscad.org) for the CAD exports. Run the tests with `python -m unittest discover tests`.

> All sample data (`sample_reviews.csv`, `sample_signals.csv`) is **synthetic**. The product names, reviews and colour stories are invented to show how the tools work.

---

## 1. Parametric CAD: `cad/`

- `tableware.scad`: one OpenSCAD file covering plate (divided, scoop lip, inner fillets), bowl, cup (weighted base, 0–2 handles), spoon (oval anti-roll grip, optional gag guard) and a flexible suction cup that snaps into a socket under the plate or bowl.
- `age_presets.json`: starting-point dimensions for 6–12 m, 12–24 m, 2–3 y and 3–5 y. **Edit this file to set your house standards**; everything else reads from it.
- `tableware.json`: presets for the OpenSCAD **Customizer** (Window → Customizer → choose a preset, then drag sliders). Regenerate it with `python cad/build.py --customizer`.

```bash
python cad/build.py --list                                   # see presets
python cad/build.py --age 12-24m --product plate             # one part
python cad/build.py --age 2-3y --product bowl --set bowl_diameter=140 --set scoop_lip=5
python cad/build.py --age all --product all --material pp    # whole range, mass in PP
```

The report flags tip angles under 20° and parts that could fit the small-parts cylinder (31.7 mm). It's a bounding-box screen, not a substitute for lab testing.

## 2. Competitor review analyser: `reviews/`

Feed it a CSV of reviews. Column names are auto-detected (`text/review/body`, `rating/stars`, `product/asin/brand`, `date`, `title`).

```bash
python reviews/analyze_reviews.py my_reviews.csv --out out/reviews
```

- The **opportunity index** combines how often a complaint appears in negative reviews, how low those reviews score, and how many competitors share it. Problems every brand has are your openings.
- **Run one product category at a time** (e.g. only plates). Otherwise category-specific problems like suction get diluted by products that can't have them.
- Edit `themes.json` to add complaint themes and phrasings. The report lists recurring negative phrases that no theme caught yet.
- Collect reviews in ways each site allows (your own store exports, retailer APIs, bought datasets, manual copying).

## 3. Compliance checklist: `compliance/`

```bash
python compliance/checklist.py --name "Scoop plate" --product plate \
    --materials silicone,pp --min-age-months 6 --markets US,EU,UK \
    --features suction,printed_decoration,dishwasher_claim \
    --claims "BPA-free, eco-friendly, dishwasher safe"
python compliance/checklist.py ... --claims-file packaging_copy.txt
```

- The HTML checklist has tick boxes and notes fields (saved in your browser), plus a Markdown copy for specs and tickets.
- `rules.json` holds about 45 requirements: CPSIA/CPC, lead, phthalates, small parts, FDA food contact, Prop 65, state PFAS laws, EU 1935/2004, 10/2011, the BPA ban (2024/3190), BfR XV silicone, EN 14372, EN 14350, GPSR, REACH, PPWR, plus UK, Canada and Australia, and performance tests like dishwasher, microwave and suction.
- `claims.json` covers more than 15 claim patterns ("non-toxic", "eco-friendly", "biodegradable", "antibacterial", "pediatrician recommended", …). It includes the EU ban on generic green claims from **27 Sept 2026** (Directive 2024/825).
- **Not legal advice.** The knowledge base was last reviewed in 2026-10. Confirm with an accredited lab or compliance consultant, and update `rules.json` as rules change.

## 4. Colour trend forecaster: `palette/`

Colours usually appear first in **forecasts, adult fashion and interiors**, then in **kidswear and nursery**, and then in **children's tableware**. The tool tracks colour "signals" from each of those stages over time and projects them forward.

**Workflow**

1. **Log signals every month or quarter** into a CSV (`date, hex, source_type, source_name, weight, notes`). Source types and their weights are in `sources.json`: `forecast_agency`, `adult_fashion`, `interiors`, `social`, `kids_fashion`, `nursery_interiors`, `competitor_launch`, `retail_bestseller`, `own_sales`.
2. **Pull colours from photos** (trade-show shots, competitor launches, Pinterest boards):
   ```bash
   python palette/extract_colors.py photos/*.jpg --source-type kids_fashion \
       --source-name "Playtime Paris Jan 2026" --date 2026-01-20 --signals signals.csv
   ```
3. **Forecast**:
   ```bash
   python palette/trendcast.py signals.csv --horizon 4 --library supplier_colours.csv
   ```

**Output**
- **Colour families** labelled Emerging, Rising, Peak, Stable or Declining, with the share of upstream sources (pipeline) against the kids market, the whitespace between them, and a 12-month projection.
- A **launch palette** (hero + supporting + neutral), with checks for:
  - **Food camouflage**: whether peas disappear on a green plate (`food_colors.json`).
  - **Colour-blind distinguishability**: protan, deutan and tritan simulation.
  - **Nearest supplier colour**: pass `--library name,hex`, e.g. a masterbatch card, to check you can actually make it.

**Tips:** log with similar effort per source each quarter, keep at least 4–6 quarters of history, and add your own sell-through as `own_sales` (weight = units/100). Tune `--adoption` (how much of the upstream gap closes in a year) against what actually happened to past colours.
