import unittest

from scamshield.core.sources import capability_coverage, safe_verdict_coverage


class CapabilityCoverageTests(unittest.TestCase):
    def test_market_source_alone_cannot_prove_token_safety(self):
        result = capability_coverage(
            [{"name": "dexscreener", "status": "clean"}],
            "token",
        )
        self.assertEqual(result["assessment_status"], "partial")
        self.assertIn("market_data", result["available_capabilities"])
        self.assertIn("sellability", result["missing_capabilities"])
        self.assertIn("holder_distribution", result["missing_capabilities"])

    def test_failed_security_provider_remains_missing(self):
        result = capability_coverage(
            [
                {"name": "dexscreener", "status": "clean"},
                {"name": "honeypot", "status": "timeout"},
            ],
            "token",
        )
        self.assertIn("sellability", result["failed_capabilities"])
        self.assertNotIn("sellability", result["available_capabilities"])

    def test_explicit_capabilities_support_new_providers(self):
        result = capability_coverage(
            [{"name": "future_provider", "status": "observed", "capabilities": ["chain_state", "transaction_history", "threat_reputation"]}],
            "wallet",
        )
        self.assertEqual(result["assessment_status"], "available")
        self.assertEqual(result["coverage_ratio"], 1.0)

    def test_no_sources_is_insufficient(self):
        result = capability_coverage([], "wallet")
        self.assertEqual(result["assessment_status"], "insufficient_data")

    def test_wallet_cannot_be_called_safe_without_chain_history(self):
        report = capability_coverage(
            [{"name": "noytrix_scam_database", "status": "clean"}],
            "wallet",
        )
        safety = safe_verdict_coverage(report, "wallet")
        self.assertFalse(safety["eligible"])
        self.assertIn("chain_state", safety["missing_capabilities"])
        self.assertIn("transaction_history", safety["missing_capabilities"])

    def test_contract_safety_requires_control_coverage(self):
        report = capability_coverage(
            [
                {"name": "etherscan", "status": "clean"},
                {"name": "noytrix_scam_database", "status": "clean"},
            ],
            "contract",
        )
        safety = safe_verdict_coverage(report, "contract")
        self.assertFalse(safety["eligible"])
        self.assertIn("token_controls", safety["missing_capabilities"])


if __name__ == "__main__":
    unittest.main()
