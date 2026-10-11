import unittest

from scamshield.intelligence.wallet_exposure import check_counterparty_reputation, correlate_counterparties, normalize_nft_approvals, normalize_token_approvals


class WalletExposureTests(unittest.TestCase):
    def test_unlimited_exposure_is_current_balance(self):
        rows = normalize_token_approvals([{"token_address": "0xt", "balance": "12.5", "approved_list": [{"approved_contract": "0xs", "approved_amount": "Unlimited", "address_info": {}}]}])
        self.assertEqual(rows[0]["exposed_units"], 12.5)
        self.assertTrue(rows[0]["unlimited"])

    def test_limited_exposure_cannot_exceed_balance(self):
        rows = normalize_token_approvals([{"token_address": "0xt", "balance": "4", "approved_list": [{"approved_contract": "0xs", "approved_amount": "10", "address_info": {}}]}])
        self.assertEqual(rows[0]["exposed_units"], 4.0)

    def test_only_explicit_malicious_behavior_is_confirmed(self):
        rows = normalize_token_approvals([{"token_address": "0xt", "balance": "1", "approved_list": [{"approved_contract": "0xs", "approved_amount": "Unlimited", "address_info": {"doubt_list": 1, "malicious_behavior": []}}]}])
        self.assertTrue(rows[0]["doubt_list"])
        self.assertEqual(rows[0]["confirmed_malicious_behaviors"], [])

    def test_nft_all_approval_is_preserved(self):
        rows = normalize_nft_approvals([{"nft_address": "0xn", "approved_list": [{"approved_contract": "0xs", "approved_for_all": 1, "address_info": {}}]}], "erc721")
        self.assertTrue(rows[0]["approved_for_all"])

    def test_counterparty_contact_policy_cannot_accuse_wallet(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        with patch("scamshield.intelligence.wallet_exposure.check_address_reputation", new=AsyncMock(return_value={"address": "0xbad", "status": "malicious", "confirmed_behaviors": ["stealing_attack"]})):
            result = asyncio.run(check_counterparty_reputation(["0xbad"], "1"))
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["verdict"], "unknown")
        self.assertFalse(result["evidence"][0]["hard_evidence"])

    def test_database_counterparty_match_is_context_only(self):
        result = correlate_counterparties(["0xbad"], lambda _address: {"matched": True, "status": "malicious", "level": "critical", "risk_score": 95, "confidence": 90, "force_verdict": True, "database": "test"})
        self.assertEqual(result["verdict"], "unknown")
        self.assertFalse(result["evidence"][0]["hard_evidence"])
        self.assertEqual(result["evidence"][0]["polarity"], "neutral")


if __name__ == "__main__":
    unittest.main()
