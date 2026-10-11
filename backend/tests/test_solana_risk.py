import unittest

from scamshield.intelligence.solana_risk import build_solana_risk_summary


class SolanaRiskSummaryTests(unittest.TestCase):
    def test_mint_controls_are_explained_without_becoming_a_scam_verdict(self):
        result = build_solana_risk_summary({
            "entity_type": "mint", "mint_authority": "mint", "freeze_authority": "freeze",
            "token_2022_controls": {"permanent_delegate": "delegate", "transfer_hook": {"program_id": "hook"}},
            "top10_owner_concentration_pct": 85.0,
        }, "en")
        self.assertTrue(result["available"])
        self.assertEqual(result["level"], "high_control")
        self.assertEqual(result["control_score"], 79)
        self.assertIn("not a scam verdict", result["summary"])

    def test_non_mint_is_not_presented_as_a_token_control_report(self):
        result = build_solana_risk_summary({"entity_type": "wallet_or_account"}, "uk")
        self.assertFalse(result["available"])
        self.assertEqual(result["level"], "not_applicable")
        self.assertIsNone(result["control_score"])

    def test_russian_copy_has_no_english_fallback(self):
        result = build_solana_risk_summary({"entity_type": "mint", "freeze_authority": "authority"}, "ru")
        self.assertIn("Счета токена", result["findings"][0]["title"])
