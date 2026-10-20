"""The desktop's theme choice is saved to claude/theme.json so the phone can follow it."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import server  # noqa: E402


class ThemeTest(unittest.TestCase):
    def setUp(self):
        self.notes, self.old = tempfile.mkdtemp(), server.NOTES
        server.NOTES = self.notes

    def tearDown(self):
        server.NOTES = self.old
        shutil.rmtree(self.notes)

    def test_saved_theme_is_read_back(self):
        self.assertIsNone(server.saved_theme())
        server.act_theme({"theme": "riso/auto"})
        self.assertEqual(server.saved_theme(), "riso/auto")
        self.assertIn("claude/theme.json", server.TOUCHED)

    def test_rejects_anything_but_family_slash_mode(self):
        for bad in ("", "riso", "../x/y", "Riso/Paper", None, "a/b/c"):
            with self.assertRaises(ValueError):
                server.act_theme({"theme": bad})


if __name__ == "__main__":
    unittest.main()
