"""Metacognition score maths. Run: python3 -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import predictions as P  # noqa: E402

LOG = """# Predictions
- 2026-09-27 · 70% · recommend · bet: Status, then recent · got: Status, then recent · hit
- 2026-09-27 · 60% · recommend · bet: Todos only · got: Everything · miss
- 2026-09-01 · 90% · guess · bet: wants it short · got: wanted it short · hit
- not a prediction line
- 2026-09-27 · 30% · draft · bet: too low · got: x · hit
"""


class PredictionsTest(unittest.TestCase):
    def test_parse_skips_junk_and_clamps_below_50(self):
        e = P.parse(LOG)
        self.assertEqual(len(e), 4)
        self.assertEqual(e[3]["conf"], 50)
        self.assertEqual(e[1], {"date": "2026-09-27", "conf": 60, "kind": "recommend", "bet": "Todos only", "got": "Everything", "hit": False})

    def test_score_rewards_confident_hits_and_punishes_confident_misses(self):
        self.assertEqual(P.score([{"conf": 100, "hit": True}]), 100)
        self.assertEqual(P.score([{"conf": 50, "hit": True}]), 0)
        self.assertLess(P.score([{"conf": 90, "hit": False}]), P.score([{"conf": 55, "hit": False}]))
        self.assertIsNone(P.score([]))

    def test_stats_calibration_and_week_change(self):
        s = P.stats(P.parse(LOG), today="2026-09-27")
        self.assertEqual(s["n"], 4)
        self.assertEqual(s["hit_rate"], 75)
        self.assertEqual(s["entries"][0]["bet"], "too low")  # newest first
        self.assertEqual({b["conf"] for b in s["buckets"]}, {50, 60, 70, 90})
        self.assertIsNotNone(s["week_change"])  # the Sept 1 entry is older than a week
        self.assertEqual(P.stats([])["n"], 0)


if __name__ == "__main__":
    unittest.main()
