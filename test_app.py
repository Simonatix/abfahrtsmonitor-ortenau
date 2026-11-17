import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

os.environ["EFA_MOCK_DIR"] = str(Path(__file__).resolve().parent / "fixtures")

import app


class ParseTests(unittest.TestCase):
    def test_search_stops_parses_fixture(self):
        stops = app.search_stops("Achern")
        self.assertTrue(any(s["gid"] == "de:08317:33013" and "Achern" in s["name"] for s in stops))

    def test_search_stops_restricted_to_ortenaukreis(self):
        stops = app.search_stops("Offenburg Hbf")
        self.assertTrue(stops)
        self.assertTrue(all(s["gid"].startswith("de:08317:") for s in stops))
        self.assertEqual(stops[0]["gid"], "de:08317:14506")

    def test_departures_mixed_stop(self):
        data = app.get_departures("de:08317:33013")
        self.assertEqual(data["stop"]["gid"], "de:08317:33013")
        deps = data["departures"]
        self.assertGreater(len(deps), 10)
        for dep in deps:
            self.assertRegex(dep["planned"], r"^\d{2}:\d{2}$")
            self.assertRegex(dep["real"], r"^\d{2}:\d{2}$")
            self.assertIn(dep["kind"], ("bus", "bahn", "other"))
            self.assertTrue(dep["line"])
            self.assertTrue(dep["direction"])
        kinds = {d["kind"] for d in deps}
        self.assertIn("bus", kinds)
        self.assertIn("bahn", kinds)
        cancelled = [d for d in deps if d["cancelled"]]
        self.assertTrue(cancelled)
        self.assertTrue(all(d["delay"] is None for d in cancelled))
        ordered = [(d["plannedDate"], d["real"]) for d in deps]
        self.assertEqual(ordered, sorted(ordered))

    def test_departures_train_only_stop(self):
        data = app.get_departures("de:08317:15810")
        self.assertTrue(data["departures"])
        self.assertTrue(all(d["kind"] == "bahn" for d in data["departures"]))

    def test_departures_bus_only_stop(self):
        data = app.get_departures("de:08317:11902")
        self.assertTrue(data["departures"])
        self.assertTrue(all(d["kind"] == "bus" for d in data["departures"]))

    def test_mock_unknown_stop_raises_404(self):
        with self.assertRaises(app.EfaError) as ctx:
            app.get_departures("de:08317:99999")
        self.assertEqual(ctx.exception.status, 404)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as response:
            return response.status, response.read()

    def test_index_page(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Abfahrtsmonitor Ortenaukreis".encode("utf-8"), body)

    def test_static_assets(self):
        for asset in ("/static/app.js", "/static/style.css"):
            status, _ = self.get(asset)
            self.assertEqual(status, 200, asset)

    def test_stops_api(self):
        status, body = self.get("/api/stops?q=Achern")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["query"], "Achern")
        self.assertTrue(any(s["gid"] == "de:08317:33013" for s in data["stops"]))

    def test_stops_api_rejects_short_query(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/stops?q=A")
        self.assertEqual(ctx.exception.code, 400)

    def test_departures_api(self):
        status, body = self.get("/api/departures?stop=de:08317:14506")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["stop"]["name"].startswith("Offenburg"))
        self.assertGreater(len(data["departures"]), 10)
        self.assertTrue(data["serverTime"])

    def test_departures_api_requires_stop(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/departures")
        self.assertEqual(ctx.exception.code, 400)

    def test_departures_api_unknown_stop(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/departures?stop=de:08317:99999")
        self.assertEqual(ctx.exception.code, 404)
        body = json.loads(ctx.exception.read())
        self.assertIn("error", body)

    def test_unknown_route(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_static_path_traversal_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/static/..%2Fapp.py")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
