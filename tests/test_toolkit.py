"""Run with: python -m unittest discover tests"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for sub in ("reviews", "compliance", "palette", "cad"):
    sys.path.insert(0, str(ROOT / sub))

from tablekit import colorsci  # noqa: E402


class ColourScience(unittest.TestCase):
    def test_de2000_reference_pairs(self):
        # Sharma, Wu & Dalal (2005) test data
        pairs = [((50, 2.6772, -79.7751), (50, 0, -82.7485), 2.0425),
                 ((50, -1.3802, -84.2814), (50, 0, -82.7485), 1.0000),
                 ((50, 2.5, 0), (50, 0, -2.5), 4.3065),
                 ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
                 ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373)]
        for a, b, expected in pairs:
            self.assertAlmostEqual(colorsci.delta_e2000(a, b), expected, places=3)

    def test_lab_roundtrip(self):
        for h in ("#F2E2A0", "#5E3B2E", "#00897B", "#FFFFFF", "#000000"):
            self.assertEqual(colorsci.lab_to_hex(colorsci.hex_to_lab(h)), h)

    def test_names(self):
        self.assertEqual(colorsci.color_name("#A6B79A"), "sage")
        self.assertEqual(colorsci.color_name("#E5DBCA"), "oatmeal")
        self.assertEqual(colorsci.color_name("#1F3A5F"), "navy")

    def test_cvd_red_green_confusion(self):
        red, green = "#C0392B", "#6B8E23"
        normal = colorsci.delta_e2000(colorsci.hex_to_lab(red), colorsci.hex_to_lab(green))
        sim = colorsci.delta_e2000(colorsci.hex_to_lab(colorsci.simulate_cvd(red, "deuteranopia")),
                                   colorsci.hex_to_lab(colorsci.simulate_cvd(green, "deuteranopia")))
        self.assertLess(sim, normal / 2)


class Reviews(unittest.TestCase):
    def test_sample_analysis(self):
        import analyze_reviews as ar
        res = ar.analyze(ar.load_reviews(ROOT / "reviews/sample_reviews.csv"),
                         json.loads((ROOT / "reviews/themes.json").read_text()))
        labels = {t["theme"]: t for t in res["themes"]}
        self.assertGreaterEqual(labels["suction_failure"]["negative_mentions"], 3)
        self.assertGreaterEqual(labels["mold_hygiene"]["negative_mentions"], 4)
        self.assertTrue(any("textured trays" in w["wish"] for w in res["wishes"]))


class Compliance(unittest.TestCase):
    def spec(self, **kw):
        base = {"name": "t", "product": "plate", "materials": ["silicone"], "min_age_months": 6,
                "markets": ["US", "EU"], "features": [], "claims": ""}
        base.update(kw)
        return base

    def test_age_and_material_filters(self):
        import checklist
        young = {r["id"] for r in checklist.build(self.spec())["rules"]}
        older = {r["id"] for r in checklist.build(self.spec(min_age_months=60))["rules"]}
        self.assertIn("US-SMALLPARTS", young)
        self.assertNotIn("US-SMALLPARTS", older)
        self.assertIn("EU-SILICONE", young)
        self.assertNotIn("EU-PLASTICS", young)  # silicone isn't a plastic under 10/2011

    def test_bamboo_flags(self):
        import checklist
        res = checklist.build(self.spec(materials=["bamboo_composite"], features=["microwave_use"],
                                        claims="natural bamboo, eco-friendly"))
        self.assertIn("EU-BAMBOO", {r["id"] for r in res["rules"]})
        self.assertEqual(len(res["flags"]), 2)
        self.assertEqual(res["claims"][0]["risk"], "high")


class Palette(unittest.TestCase):
    def test_demo_stages(self):
        import trendcast as tc
        rows = tc.load_signals(ROOT / "palette/sample_signals.csv")
        cents = tc.cluster(rows, 12)
        _, clusters = tc.metrics(rows, cents, 4, 0.5, 6)
        stage = {c["name"]: c["stage"] for c in clusters}
        self.assertEqual(stage["butter yellow"], "Emerging")
        self.assertEqual(stage["mint"], "Declining")
        self.assertEqual(len(clusters), 10)


class Cad(unittest.TestCase):
    def test_small_parts(self):
        import build
        self.assertTrue(build.small_parts_flag([20, 20, 40]).startswith("FAIL"))
        self.assertTrue(build.small_parts_flag([200, 200, 25]).startswith("pass"))

    def test_presets_complete(self):
        presets = json.loads((ROOT / "cad/age_presets.json").read_text())
        for grp in presets["age_groups"].values():
            for prod in ("plate", "bowl", "cup", "spoon"):
                self.assertIn(prod, grp)


if __name__ == "__main__":
    unittest.main()
