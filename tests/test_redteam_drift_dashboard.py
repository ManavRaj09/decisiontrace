import json
import threading
import unittest
import urllib.request

from decisiontrace import Store, redteam
from decisiontrace.dashboard import make_server
from decisiontrace.demo import make_hardened_agent, make_naive_agent, seed_demo
from decisiontrace.drift import detect


class RedTeamTests(unittest.TestCase):
    def test_naive_fails_hardened_passes(self):
        c = redteam.new_canary()
        self.assertEqual(redteam.run(make_naive_agent(c), c)["passed"], 0)
        self.assertEqual(redteam.run(make_hardened_agent(c), c)["score"], 1.0)


class DriftAndDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store(":memory:")
        seed_demo(cls.store)

    def test_drift_flags_runaway_trace(self):
        metrics = {a["metric"] for a in detect(self.store, "support-agent")}
        self.assertEqual(metrics, {"steps", "cost_usd", "violations"})

    def test_dashboard_api(self):
        server = make_server(self.store, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            self.assertIn(b"DecisionTrace", urllib.request.urlopen(base + "/").read())
            traces = json.load(urllib.request.urlopen(base + "/api/traces"))
            self.assertEqual(len(traces), 15)
            exp = json.load(urllib.request.urlopen(f"{base}/api/traces/{traces[0]['id']}/explain"))
            self.assertIn("Verdict", exp["text"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
