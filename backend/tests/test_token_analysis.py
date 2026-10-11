import unittest

from scamshield.intelligence.token_analysis import (
    build_token_snapshot,
    evm_platform_candidates,
    normalize_honeypot_payload,
    platform_chain_id,
    select_dex_pairs,
)


class TokenAnalysisTests(unittest.TestCase):
    def test_platform_mapping_never_defaults_to_bsc(self):
        self.assertEqual(platform_chain_id("ethereum"), "1")
        self.assertEqual(platform_chain_id("base"), "8453")
        self.assertIsNone(platform_chain_id("unknown-chain"))

    def test_candidates_preserve_exact_platform_chain(self):
        address = "0x" + "1" * 40
        rows = evm_platform_candidates(
            {"ethereum": address, "base": address, "unknown-chain": address},
            lambda value: value.startswith("0x") and len(value) == 42,
        )
        self.assertEqual({row["chain_id"] for row in rows}, {"1", "8453"})
        self.assertNotIn("56", {row["chain_id"] for row in rows})

    def test_dex_pair_selection_uses_matching_highest_liquidity_pair(self):
        address = "0x" + "a" * 40
        wrong = {"baseToken": {"address": "0x" + "b" * 40}, "liquidity": {"usd": 999999}}
        low = {"baseToken": {"address": address}, "liquidity": {"usd": 10}, "pairAddress": "low"}
        high = {"quoteToken": {"address": address}, "liquidity": {"usd": 500}, "pairAddress": "high"}
        selected = select_dex_pairs([wrong, low, high], address)
        self.assertEqual(selected["pair_count"], 2)
        self.assertEqual(selected["primary_pair"]["pairAddress"], "high")
        self.assertEqual(selected["token_role"], "quote")

    def test_confirmed_honeypot_is_hard_evidence(self):
        result = normalize_honeypot_payload({
            "simulationSuccess": True,
            "honeypotResult": {"isHoneypot": True},
            "simulationResult": {"sellTax": 100},
        })
        self.assertEqual(result["status"], "malicious")
        self.assertTrue(any(item["code"] == "honeypot_detected" and item["hard_evidence"] for item in result["findings"]))

    def test_provider_risk_label_without_simulation_is_not_hard_evidence(self):
        result = normalize_honeypot_payload({"summary": {"risk": "high", "riskLevel": 4}})
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["assessment_status"], "partial")
        self.assertEqual(result["findings"], [])

    def test_clean_requires_successful_simulation(self):
        uncertain = normalize_honeypot_payload({"honeypotResult": {"isHoneypot": False}})
        clean = normalize_honeypot_payload({"simulationSuccess": True, "honeypotResult": {"isHoneypot": False}})
        self.assertEqual(uncertain["status"], "observed")
        self.assertEqual(clean["status"], "clean")

    def test_snapshot_preserves_unknown_metrics_as_none(self):
        snapshot = build_token_snapshot(
            {"token": {"symbol": "ABC"}, "liquidity": {"usd": 1000}},
            {"simulation_success": True, "is_honeypot": False},
        )
        self.assertEqual(snapshot["market"]["liquidity_usd"], 1000)
        self.assertIsNone(snapshot["holders"]["total"])
        self.assertIn("holders.total", snapshot["missing_metrics"])
        self.assertFalse(snapshot["complete"])

    def test_snapshot_includes_solana_authorities_and_owner_concentration(self):
        snapshot = build_token_snapshot({}, {}, {
            "mint_authority": "mint-auth",
            "freeze_authority": None,
            "largest_owner_sample": [{"owner": "a", "supply_pct": 55}],
            "top10_owner_concentration_pct": 70.0,
            "largest_owner_sample_complete": True,
            "token_2022_controls": {"non_transferable": True},
        })
        self.assertEqual(snapshot["controls"]["mint_authority"], "mint-auth")
        self.assertEqual(snapshot["holders"]["concentration_top_10_pct"], 70.0)
        self.assertNotIn("controls.owner_or_authority", snapshot["missing_metrics"])
        self.assertTrue(snapshot["controls"]["token_2022"]["non_transferable"])


if __name__ == "__main__":
    unittest.main()
