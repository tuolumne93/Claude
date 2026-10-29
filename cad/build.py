#!/usr/bin/env python3
"""Batch-export the parametric tableware models and run quick design checks.

Examples
  python cad/build.py --list
  python cad/build.py --age 12-24m --product plate
  python cad/build.py --age all --product all --material silicone
  python cad/build.py --age 2-3y --product bowl --set bowl_diameter=140 --set scoop_lip=5
  python cad/build.py --customizer        # refresh tableware.json presets for the OpenSCAD GUI

For every exported part it reports capacity, volume, estimated mass, how far it
can be tilted before it tips over (empty), and a small-parts screening flag.
Needs OpenSCAD on PATH (https://openscad.org); numpy for the mesh checks.
"""

import argparse
import json
import math
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from tablekit.report import esc, page, table  # noqa: E402

SCAD = HERE / "tableware.scad"
PRESETS = json.loads((HERE / "age_presets.json").read_text())
PRODUCTS = ["plate", "bowl", "cup", "spoon"]

# Small parts cylinder (US 16 CFR 1501): 31.7 mm diameter, 25.4-57.1 mm deep.
SMALL_PARTS_D = 31.7
SMALL_PARTS_DEPTH = 57.1


def scad_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(str(v))


def parse_set(pairs):
    out = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        v = v.strip()
        if v.lower() in ("true", "false"):
            out[k.strip()] = v.lower() == "true"
        else:
            try:
                out[k.strip()] = float(v) if "." in v else int(v)
            except ValueError:
                out[k.strip()] = v.strip('"')
    return out


def params_for(age, product, overrides):
    p = dict(PRESETS["age_groups"][age][product]) if product != "suction_cup" else {}
    if product == "suction_cup":
        # size the suction cup to the plate preset of the same age group
        p["suction_skirt_d"] = 110
    p.update(overrides)
    p["product"] = product
    return p


# --- mesh checks ------------------------------------------------------------

def load_stl(path):
    import numpy as np
    data = Path(path).read_bytes()
    if data[:5].lower() == b"solid" and b"facet" in data[:400]:
        nums = re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)
        v = np.array(nums, dtype=float)
    else:
        n = struct.unpack("<I", data[80:84])[0]
        rec = np.frombuffer(data[84:84 + n * 50], dtype=np.dtype([
            ("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
        v = rec["v"].reshape(-1, 3).astype(float)
    return v.reshape(-1, 3, 3)


def mesh_stats(tris):
    import numpy as np
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    signed = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    vol = signed.sum()
    com = ((a + b + c) / 4.0 * signed[:, None]).sum(axis=0) / vol
    pts = tris.reshape(-1, 3)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    # base contact points: everything within 0.3 mm of the lowest point
    base = pts[pts[:, 2] < lo[2] + 0.3][:, :2]
    tip = None
    if len(base) >= 3:
        rel = base - com[:2]
        worst = min(
            (rel @ np.array([math.cos(t), math.sin(t)])).max()
            for t in np.linspace(0, 2 * math.pi, 72, endpoint=False))
        h = com[2] - lo[2]
        tip = math.degrees(math.atan2(max(worst, 0.0), h)) if h > 0 else 90.0
    return {"volume_cm3": abs(vol) / 1000.0, "bbox_mm": (hi - lo).tolist(),
            "com_height_mm": float(com[2] - lo[2]), "tip_angle_deg": tip}


def small_parts_flag(bbox, flexible=False):
    a, b, c = sorted(bbox)
    if math.hypot(a, b) <= SMALL_PARTS_D and c <= SMALL_PARTS_DEPTH:
        return "FAIL - fits small parts cylinder"
    if flexible:
        return "check - flexible part; test compressed and after abuse tests"
    if a <= SMALL_PARTS_D and c <= SMALL_PARTS_DEPTH * 1.2:
        return "check - may fit at an angle; test physically"
    return "pass (screening)"


# --- main ---------------------------------------------------------------------

def run_openscad(params, out_stl, fn):
    exe = shutil.which("openscad")
    cmd = [exe or "openscad", "-o", str(out_stl), "-D", f"$fn={fn}"]
    for k, v in params.items():
        cmd += ["-D", f"{k}={scad_value(v)}"]
    cmd.append(str(SCAD))
    if not exe:
        print("OpenSCAD not found. Install it from https://openscad.org, or run:\n  "
              + " ".join(f"'{c}'" if " " in c or '"' in c else c for c in cmd))
        return None
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        raise SystemExit(f"OpenSCAD failed for {out_stl.name}")
    m = re.search(r"CAPACITY_ML=([\d.eE+-]+)", res.stderr + res.stdout)
    return float(m.group(1)) if m else None


def write_customizer():
    sets = {}
    for age, grp in PRESETS["age_groups"].items():
        for prod in PRODUCTS:
            p = params_for(age, prod, {})
            sets[f"{age} {prod}"] = {k: scad_value(v).strip('"') for k, v in p.items()}
    out = HERE / "tableware.json"
    out.write_text(json.dumps({"fileFormatVersion": "1", "parameterSets": sets}, indent=2))
    print(f"wrote {out} ({len(sets)} parameter sets)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--age", default="12-24m", help="age group key, or 'all'")
    ap.add_argument("--product", default="plate", help="plate|bowl|cup|spoon|suction_cup|all")
    ap.add_argument("--set", action="append", metavar="NAME=VALUE", help="override a model parameter")
    ap.add_argument("--material", default="silicone", help="for mass estimate: " + ", ".join(PRESETS["materials_g_per_cm3"]))
    ap.add_argument("--out", default="out/cad", help="output folder")
    ap.add_argument("--fn", type=int, default=96, help="curve smoothness")
    ap.add_argument("--list", action="store_true", help="show age groups and presets")
    ap.add_argument("--customizer", action="store_true", help="write tableware.json for the OpenSCAD Customizer")
    args = ap.parse_args()

    if args.list:
        for age, grp in PRESETS["age_groups"].items():
            print(f"{age:8} {grp['label']}")
            for prod in PRODUCTS:
                print(f"         {prod:6} {grp[prod]}")
        return
    if args.customizer:
        write_customizer()
        return

    ages = list(PRESETS["age_groups"]) if args.age == "all" else [args.age]
    prods = PRODUCTS + ["suction_cup"] if args.product == "all" else [args.product]
    for a in ages:
        if a not in PRESETS["age_groups"]:
            raise SystemExit(f"unknown age group {a!r}; try --list")
    density = PRESETS["materials_g_per_cm3"].get(args.material)
    if density is None:
        raise SystemExit(f"unknown material {args.material!r}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    overrides = parse_set(args.set)
    rows, summary = [], []
    for age in ages:
        for prod in prods:
            if prod == "suction_cup" and not PRESETS["age_groups"][age]["plate"].get("suction_mount"):
                continue
            params = params_for(age, prod, overrides)
            stl = out / f"{prod}_{age}.stl"
            print(f"exporting {stl} ...")
            cap = run_openscad(params, stl, args.fn)
            if not stl.exists():
                continue
            s = mesh_stats(load_stl(stl))
            s.update(age=age, product=prod, file=stl.name, capacity_ml=cap,
                     mass_g=s["volume_cm3"] * density, material=args.material,
                     small_parts=small_parts_flag(s["bbox_mm"], flexible=prod == "suction_cup"),
                     under_3=PRESETS["age_groups"][age]["min_age_months"] < 36,
                     params=params)
            summary.append(s)
            tip = s["tip_angle_deg"]
            tip_txt = "-" if tip is None or prod == "spoon" else f"{tip:.0f}°" + (" (low!)" if tip < 20 else "")
            rows.append([age, prod, "×".join(f"{d:.0f}" for d in s["bbox_mm"]),
                         "-" if cap is None else (f"{cap:.1f}" if cap < 20 else f"{cap:.0f}"), f"{s['mass_g']:.0f}",
                         tip_txt, s["small_parts"] if s["under_3"] else "n/a (3y+)", stl.name])

    if not summary:
        return
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    headers = ["Age", "Product", "Size mm (x×y×z)", "Capacity ml", f"Mass g ({args.material})",
               "Tip angle (empty)", "Small parts", "STL"]
    body = (table(headers, rows)
            + "<p class='small muted'>Tip angle: how far the empty part can be tilted before it falls over "
              "(higher is better; with food or a filled cup the centre of mass rises). Small-parts check is a "
              "bounding-box screen only, for products intended for children under 3 and for detachable parts "
              "such as suction cups; confirm with a physical test at an accredited lab. Capacity is the "
              "approximate food space to the rim (plates/bowls) or brim (cups).</p>")
    (out / "report.html").write_text(page("Tableware CAD build report", body,
                                          f"{len(summary)} parts · material {args.material}"))
    for r in rows:
        print("  " + " | ".join(str(c) for c in r))
    print(f"\nwrote {out / 'report.html'} and {out / 'summary.json'}")


if __name__ == "__main__":
    main()
