import unittest
import sys
import types

if "httpx" not in sys.modules:
    class _Client:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
    httpx_stub = types.ModuleType("httpx")
    httpx_stub.AsyncClient = _Client
    httpx_stub.Timeout = lambda *args, **kwargs: None
    httpx_stub.TimeoutException = TimeoutError
    sys.modules["httpx"] = httpx_stub

from scamshield.intelligence.solana_rpc import (
    _largest_owner_distribution,
    normalize_token_2022_extensions,
)


class SolanaRpcTests(unittest.TestCase):
    def test_mint_metrics_and_authorities(self):
        distribution = _largest_owner_distribution(
            [{"address": "ta1", "amount": "6000"}, {"address": "ta2", "amount": "1000"}],
            [
                {"data": {"parsed": {"type": "account", "info": {"owner": "owner-1"}}}},
                {"data": {"parsed": {"type": "account", "info": {"owner": "owner-1"}}}},
            ],
            10000,
        )
        self.assertEqual(distribution["top10_owner_concentration_pct"], 70.0)
        self.assertEqual(distribution["resolved_owner_count"], 1)
        self.assertTrue(distribution["sample_complete"])

    def test_distribution_aggregates_multiple_accounts_for_same_owner(self):
        rows = [{"amount": "400"}, {"amount": "300"}, {"amount": "200"}]
        accounts = [
            {"data": {"parsed": {"info": {"owner": "a"}}}},
            {"data": {"parsed": {"info": {"owner": "a"}}}},
            {"data": {"parsed": {"info": {"owner": "b"}}}},
        ]
        result = _largest_owner_distribution(rows, accounts, 1000)
        self.assertEqual(result["resolved_owner_count"], 2)
        self.assertEqual(result["largest_owners"][0]["raw_amount"], "700")
        self.assertEqual(result["top10_owner_concentration_pct"], 90.0)

    def test_token_2022_controls_are_structured_neutral_facts(self):
        result = normalize_token_2022_extensions([
            {"extension": "transferFeeConfig", "state": {"transferFeeConfigAuthority": "fee-auth", "newerTransferFee": {"transferFeeBasisPoints": 250}}},
            {"extension": "permanentDelegate", "state": {"delegate": "delegate"}},
            {"extension": "transferHook", "state": {"authority": "hook-auth", "programId": "hook-program"}},
            {"extension": "nonTransferable"},
        ])
        controls = result["controls"]
        self.assertEqual(controls["transfer_fee"]["config_authority"], "fee-auth")
        self.assertEqual(controls["permanent_delegate"], "delegate")
        self.assertEqual(controls["transfer_hook"]["program_id"], "hook-program")
        self.assertTrue(controls["non_transferable"])
        self.assertTrue(all(item["severity"] == 0 and item["polarity"] == "neutral" for item in result["evidence"]))



if __name__ == "__main__":
    unittest.main()
