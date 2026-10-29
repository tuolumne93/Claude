#!/usr/bin/env python3
"""Pull dominant colours from photos (runway shots, competitor product photos,
trade-show snaps, Pinterest saves) and append them as signals for trendcast.py.

Examples
  python palette/extract_colors.py photos/kidswear_aw26/*.jpg --source-type kids_fashion \\
      --source-name "Playtime Paris Jan 2026" --date 2026-01-20 --signals my_signals.csv
  python palette/extract_colors.py shots/*.png --source-type competitor_launch --dry-run

Near-white and near-black studio backgrounds are skipped by default
(--keep-background to keep them). Each colour that covers at least --min-share
of the image becomes one signal, weighted by its share.
Needs numpy and Pillow.
"""

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from tablekit.colorsci import color_name, lab_to_hex  # noqa: E402

SOURCES = json.loads((HERE / "sources.json").read_text())["source_types"]


def rgb_to_lab_np(rgb):
    c = rgb / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1)


def dominant_colours(path, k=6, keep_background=False, seed=0):
    img = Image.open(path).convert("RGB")
    img.thumbnail((160, 160))
    lab = rgb_to_lab_np(np.asarray(img, dtype=float).reshape(-1, 3))
    if not keep_background:
        chroma = np.hypot(lab[:, 1], lab[:, 2])
        bg = ((lab[:, 0] > 93) & (chroma < 6)) | (lab[:, 0] < 8)
        if (~bg).sum() > 50:
            lab = lab[~bg]
    rng = np.random.default_rng(seed)
    k = min(k, len(lab))
    # k-means++ initialisation
    centres = [lab[rng.integers(len(lab))]]
    for _ in range(1, k):
        d = np.min([((lab - c) ** 2).sum(1) for c in centres], axis=0)
        centres.append(lab[rng.choice(len(lab), p=d / d.sum())] if d.sum() else lab[rng.integers(len(lab))])
    centres = np.array(centres)
    for _ in range(25):
        labels = ((lab[:, None, :] - centres[None]) ** 2).sum(2).argmin(1)
        new = np.array([lab[labels == i].mean(0) if (labels == i).any() else centres[i] for i in range(k)])
        if np.allclose(new, centres, atol=0.05):
            break
        centres = new
    shares = np.bincount(labels, minlength=k) / len(labels)
    order = np.argsort(-shares)
    return [(lab_to_hex(tuple(centres[i])), float(shares[i])) for i in order]


def date_for(path, fallback):
    if fallback:
        return fallback
    m = re.search(r"(20\d{2})[-_]?(\d{2})(?:[-_]?(\d{2}))?", path.name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3) or '15'}"
    return dt.date.fromtimestamp(path.stat().st_mtime).isoformat()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--source-type", required=True, choices=sorted(SOURCES))
    ap.add_argument("--source-name", default="")
    ap.add_argument("--date", help="YYYY-MM-DD for all images (default: from filename, else file date)")
    ap.add_argument("--signals", default="signals.csv", help="CSV to append to (created if missing)")
    ap.add_argument("-k", type=int, default=6, help="colours to find per image")
    ap.add_argument("--min-share", type=float, default=0.06, help="ignore colours covering less than this")
    ap.add_argument("--keep-background", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print, don't write")
    args = ap.parse_args()

    out_rows = []
    for p in map(Path, args.images):
        date = date_for(p, args.date)
        cols = [(h, s) for h, s in dominant_colours(p, args.k, args.keep_background) if s >= args.min_share]
        print(f"{p.name}: " + ", ".join(f"{h} {color_name(h)} {s:.0%}" for h, s in cols))
        for h, s in cols:
            out_rows.append([date, h, args.source_type, args.source_name, f"{s * 3:.2f}", p.name])

    if args.dry_run or not out_rows:
        return
    sig = Path(args.signals)
    new = not sig.exists()
    with open(sig, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date", "hex", "source_type", "source_name", "weight", "notes"])
        w.writerows(out_rows)
    print(f"appended {len(out_rows)} signals to {sig}")


if __name__ == "__main__":
    main()
