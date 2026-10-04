import unittest

from decisiontrace import pii


class PiiTests(unittest.TestCase):
    def test_email_and_card_masked(self):
        out = pii.mask("mail jane@corp.com card 4111 1111 1111 1111")
        self.assertIn("[EMAIL_REDACTED]", out)
        self.assertIn("[CREDIT_CARD_REDACTED]", out)
        self.assertNotIn("4111", out)

    def test_invalid_card_not_flagged_as_card(self):
        types = {f.type for f in pii.detect("order 1234 5678 9012 3456")}
        self.assertNotIn("CREDIT_CARD", types)

    def test_ssn_and_keys(self):
        types = {f.type for f in pii.detect("ssn 123-45-6789 key AKIAABCDEFGHIJKLMNOP token sk-abcdefghijklmnop1234")}
        self.assertEqual(types, {"SSN", "AWS_KEY", "API_KEY"})

    def test_mask_obj_nested(self):
        masked = pii.mask_obj({"a": ["x@y.com"], "n": 5})
        self.assertEqual(masked, {"a": ["[EMAIL_REDACTED]"], "n": 5})


if __name__ == "__main__":
    unittest.main()
