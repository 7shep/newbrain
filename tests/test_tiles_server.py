"""Adaptive tiles: the server serves tiles.js/css and state() carries a Map summary for the Map tile."""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import server  # noqa: E402


class RoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.Server(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_shared_assets_are_served_with_their_type(self):
        for name, ctype in (("theme.css", "text/css"), ("theme.js", "text/javascript"),
                            ("tiles.css", "text/css"), ("tiles.js", "text/javascript")):
            with self.subTest(name):
                if not os.path.exists(os.path.join(server.HERE, name)):
                    self.skipTest(f"app/{name} not written yet")
                c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1])
                c.request("GET", "/" + name)
                r = c.getresponse()
                self.assertEqual(r.status, 200)
                self.assertTrue(r.getheader("Content-Type").startswith(ctype))
                self.assertTrue(r.read())
                c.close()


class GraphSummaryTest(unittest.TestCase):
    def setUp(self):
        self.notes, self.old = tempfile.mkdtemp(), (server.NOTES, server.build.NOTES)
        server.NOTES = server.build.NOTES = self.notes

    def tearDown(self):
        server.NOTES, server.build.NOTES = self.old
        shutil.rmtree(self.notes)

    def test_no_graph_is_none(self):
        self.assertIsNone(server.state()["graph"])

    def test_a_broken_layout_file_falls_back_to_urgency_order(self):
        os.makedirs(os.path.join(self.notes, "claude"))
        with open(os.path.join(self.notes, "claude", "layout.json"), "w") as f:
            f.write('<<<<<<< HEAD\n{"order": ["next"]}\n=======\n{"order": ["map"]}\n>>>>>>> phone\n')
        self.assertEqual(server.state()["layout"], [])

    def test_hidden_tiles_and_order_are_saved_without_clobbering_each_other(self):
        server.act_layout({"order": ["next", "inbox"]})
        server.act_layout({"hidden": ["t:music", "cover"]})
        st = server.state()
        self.assertEqual((st["layout"], st["hidden"]), (["next", "inbox"], ["t:music", "cover"]))
        server.act_layout({"order": []})
        self.assertEqual(server.state()["hidden"], ["t:music", "cover"])
        for bad in ({}, {"hidden": "cover"}, {"hidden": [1]}, {"order": None}):
            with self.assertRaises(ValueError):
                server.act_layout(bad)

    def test_falls_back_to_the_published_phone_graph(self):
        # CI has no graphify-out/ (gitignored), only the phone/graph.json the Mac published
        os.makedirs(os.path.join(self.notes, "phone"))
        with open(os.path.join(self.notes, "phone", "graph.json"), "w") as f:
            json.dump({"nodes": [{"id": "a", "label": "A", "group": 0, "groupName": "Brain app / server", "file": "x.md"},
                                 {"id": "b", "label": "B", "group": 0, "groupName": "Brain app / server", "file": ""}],
                       "links": [["a", "b"]], "built": "2026-10-28"}, f)
        g = server.state()["graph"]
        self.assertEqual((g["nodes"], g["links"]), (2, 1))
        self.assertEqual(g["clusters"], [["Brain app", 2]])

    def test_summary_counts_and_top_clusters(self):
        nodes = [{"id": f"a{i}", "community": 0, "community_name": "Brain app / server"} for i in range(3)]
        nodes += [{"id": f"b{i}", "community": 1} for i in range(2)]
        nodes += [{"id": f"c{i}", "community": i + 2, "community_name": f"Solo {i}"} for i in range(6)]
        links = [{"source": "a0", "target": "a1"}, {"source": "a1", "target": "b0"}, {"source": "a0", "target": "gone"}]
        os.makedirs(os.path.join(self.notes, "graphify-out"))
        with open(os.path.join(self.notes, "graphify-out", "graph.json"), "w") as f:
            json.dump({"nodes": nodes, "links": links}, f)
        g = server.state()["graph"]
        self.assertEqual(g["nodes"], 11)
        self.assertEqual(g["links"], 2)  # the link to a missing node is trimmed, as in graph_get()
        self.assertEqual(len(g["clusters"]), 6)
        self.assertEqual(g["clusters"][:2], [["Brain app", 3], ["Cluster 1", 2]])


if __name__ == "__main__":
    unittest.main()


class CustomTilesTest(unittest.TestCase):
    def test_each_md_in_tiles_is_a_tile_and_refresh_rewrites_it(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        os.makedirs(os.path.join(d, "tiles"))
        # the refresh runs a UTF-8 script: a "·" inside the command itself gets mangled by Windows' code page
        with open(os.path.join(d, "gen.py"), "w", encoding="utf-8") as f:
            f.write("open('tiles/music.md', 'w', encoding='utf-8').write('---\\ntitle: Recently played\\n---\\n- Nights · Frank Ocean\\n')\n")
        with open(os.path.join(d, "tiles", "music.md"), "w") as f:
            f.write(f'---\ntitle: Recently played\nicon: music\nrefresh: {sys.executable} gen.py\n---\n- old\n')
        old, server.NOTES = server.NOTES, d
        self.addCleanup(setattr, server, "NOTES", old)
        allow = os.path.join(d, "refresh-allow")  # the Mac-only list; tiles arrive by git, so they can't run what isn't on it
        with open(allow, "w") as f:
            f.write(f"# tile refresh commands this Mac may run\n{sys.executable} gen.py\n")
        oldallow, server.REFRESH_ALLOW = server.REFRESH_ALLOW, allow
        self.addCleanup(setattr, server, "REFRESH_ALLOW", oldallow)
        server.REFRESHED.clear()
        (t,) = server.custom_tiles()
        self.assertEqual((t["slug"], t["title"], t["path"]), ("music", "Recently played", "tiles/music.md"))
        self.assertEqual(t["rows"], [["Nights", "Frank Ocean"]])

    def test_a_refresh_not_on_this_macs_list_never_runs(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        os.makedirs(os.path.join(d, "tiles"))
        with open(os.path.join(d, "tiles", "evil.md"), "w") as f:
            f.write("---\ntitle: Pulled from git\nrefresh: touch pwned\n---\n- row\n")
        old, oldallow = server.NOTES, server.REFRESH_ALLOW
        server.NOTES, server.REFRESH_ALLOW = d, os.path.join(d, "no-such-list")
        self.addCleanup(setattr, server, "NOTES", old)
        self.addCleanup(setattr, server, "REFRESH_ALLOW", oldallow)
        server.REFRESHED.clear()
        (t,) = server.custom_tiles()
        self.assertFalse(os.path.exists(os.path.join(d, "pwned")))
        self.assertIn("refresh-allow", t["summary"])
