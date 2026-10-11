import unittest

from scamshield.intelligence.goplus import normalize_goplus_token


class GoPlusNormalizationTests(unittest.TestCase):
    def test_zero_flags_do_not_become_clean_proof(self):
        result = normalize_goplus_token({"is_honeypot": "0", "cannot_sell_all": "0"}, "0xabc", "1")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["findings"], [])

    def test_explicit_honeypot_is_hard_evidence(self):
        result = normalize_goplus_token({"is_honeypot": "1"}, "0xabc", "1")
        finding = result["findings"][0]
        self.assertEqual(result["status"], "malicious")
        self.assertEqual(finding["code"], "goplus_honeypot_confirmed")
        self.assertTrue(finding["hard_evidence"])

    def test_cannot_sell_all_is_hard_evidence(self):
        result = normalize_goplus_token({"cannot_sell_all": "1"}, "0xabc", "56")
        self.assertTrue(any(row["code"] == "goplus_cannot_sell_all" for row in result["findings"]))

    def test_owner_controls_are_context_not_accusation(self):
        result = normalize_goplus_token({"hidden_owner": "1", "is_mintable": "1"}, "0xabc", "1")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["findings"], [])
        self.assertTrue(result["controls"]["hidden_owner"])


if __name__ == "__main__":
    unittest.main()
