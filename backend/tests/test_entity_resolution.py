import unittest

from scamshield.core.entities import canonical_entity_id, resolve_input_syntax


class EntityResolutionTests(unittest.TestCase):
    def test_evm_address_role_is_ambiguous(self):
        result = resolve_input_syntax("0x" + "a" * 40)
        self.assertEqual(result["syntax"], "evm_address")
        self.assertEqual(result["resolution_status"], "ambiguous")
        self.assertIn("wallet", result["candidate_types"])
        self.assertIn("contract", result["candidate_types"])
        self.assertIsNone(result["resolved_type"])

    def test_solana_address_is_not_assumed_wallet(self):
        result = resolve_input_syntax("11111111111111111111111111111111")
        self.assertEqual(result["syntax"], "cross_chain_address")
        self.assertEqual(result["resolution_status"], "ambiguous")
        self.assertIn("bitcoin_solana_syntax_collision", result["limitations"])
        self.assertIn("token", result["candidate_types"])
        self.assertIn("program", result["candidate_types"])

    def test_unambiguous_bech32_bitcoin_address_is_resolved(self):
        result = resolve_input_syntax("bc1qexampleaddress0000000000000000000000000")
        self.assertEqual(result["syntax"], "bitcoin_address")
        self.assertEqual(result["resolved_type"], "wallet")

    def test_ticker_is_explicitly_ambiguous(self):
        result = resolve_input_syntax("USDC")
        self.assertEqual(result["route_kind"], "ticker")
        self.assertEqual(result["resolution_status"], "ambiguous")
        self.assertIn("ticker_not_unique", result["limitations"])
        self.assertEqual(canonical_entity_id(result), "ticker:ambiguous:USDC")

    def test_domain_is_normalized(self):
        result = resolve_input_syntax("Example.COM")
        self.assertEqual(result["resolved_type"], "website")
        self.assertEqual(result["normalized"], "example.com")
        self.assertEqual(canonical_entity_id(result), "website:example.com")

    def test_url_fragment_is_removed_from_identity(self):
        result = resolve_input_syntax("HTTPS://Example.COM/path#secret")
        self.assertEqual(result["normalized"], "https://example.com/path")


if __name__ == "__main__":
    unittest.main()
