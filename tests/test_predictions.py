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


class CalibrationLineTest(unittest.TestCase):
    def run_hook(self, lines):
        import subprocess, tempfile
        notes = tempfile.mkdtemp()
        os.makedirs(os.path.join(notes, "codex"))
        with open(os.path.join(notes, "codex", "predictions.md"), "w", encoding="utf-8") as f:
            f.write("# Predictions\n" + "\n".join(lines) + "\n")
        hook = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "session_start.py")
        return subprocess.run([sys.executable, hook], capture_output=True, encoding="utf-8", env={**os.environ, "BRAIN_NOTES": notes}).stdout

    def test_too_few_bets_says_nothing(self):
        self.assertNotIn("Calibration", self.run_hook(["- 2026-09-27 · 70% · draft · bet: a · got: b · miss"] * 4))

    def test_advice_needs_three_bets_of_a_kind(self):
        out = self.run_hook(["- 2026-09-27 · 70% · draft · bet: a · got: b · miss"] * 3 + ["- 2026-09-27 · 60% · habit · bet: c · got: d · miss"] * 2)
        self.assertIn("offer 2 short versions", out)
        self.assertNotIn("habit-driven", out)  # only 2 habit bets
        self.assertIn('bet "c", got "d"', out)
