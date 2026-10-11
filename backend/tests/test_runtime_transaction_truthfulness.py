import asyncio
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    stub = types.ModuleType("httpx")

    class TimeoutException(Exception):
        pass

    class Timeout:
        def __init__(self, *args, **kwargs):
            pass

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    stub.TimeoutException = TimeoutException
    stub.Timeout = Timeout
    stub.AsyncClient = AsyncClient
    sys.modules["httpx"] = stub

from scamshield.runtime.approve import build_approve_runtime_fields
from scamshield.runtime.evm_simulation import RpcError, simulate_evm_transaction
from scamshield.runtime.execution_graph import build_recursive_execution_graph
from scamshield.runtime.drain_simulator import simulate_wallet_drain
from scamshield.runtime.signature_simulator import MAX_UINT_256_STR, simulate_signature


WALLET = "0x1111111111111111111111111111111111111111"
TOKEN = "0x2222222222222222222222222222222222222222"
SPENDER = "0x3333333333333333333333333333333333333333"


class RuntimeTruthfulnessTests(unittest.TestCase):
    def test_unknown_unlimited_approval_is_not_confirmed_attack(self):
        result = build_approve_runtime_fields(
            {"type": "erc20_approve", "unlimited": True, "spender": SPENDER},
            {"trust": "unknown", "risk": "unknown"},
        )
        self.assertFalse(result["confirmed_red_flag"])
        self.assertLess(result["score"], 70)
        self.assertEqual(result["drain_probability"], 0)

    def test_malicious_spender_remains_confirmed(self):
        result = build_approve_runtime_fields(
            {"type": "erc20_approve", "unlimited": True, "spender": SPENDER},
            {"trust": "malicious", "risk": "critical"},
        )
        self.assertTrue(result["confirmed_red_flag"])
        self.assertGreaterEqual(result["score"], 90)

    def test_permit_is_permission_context_not_confirmed_attack(self):
        result = simulate_signature({
            "method": "eth_signTypedData_v4",
            "typedData": {
                "primaryType": "Permit",
                "domain": {"verifyingContract": TOKEN},
                "message": {"owner": WALLET, "spender": SPENDER, "value": MAX_UINT_256_STR, "deadline": "2000000000"},
            },
        })
        self.assertTrue(result["permissions_summary"]["can_spend"])
        self.assertTrue(result["permissions_summary"]["unlimited"])
        self.assertFalse(result["permissions_summary"]["threat_confirmed"])
        self.assertLess(result["score"], 70)

    def test_selector_bytes_inside_payload_are_not_a_confirmed_attack_chain(self):
        graph = build_recursive_execution_graph("0x12345678" + "00" * 32 + "23b872dd" + "00" * 64)
        self.assertLess(graph["attack_chain_score"], 70)
        self.assertNotIn(graph["attack_chain_level"], {"high", "critical"})

    def test_unlimited_permission_does_not_invent_theft_probability(self):
        result = simulate_wallet_drain(
            {"type": "erc20_approve"},
            {"unlimited": True, "spender_trust": "unknown"},
            {},
            {},
        )
        self.assertEqual(result["drain_probability"], 0)
        self.assertEqual(result["drain_probability_basis"], "not_measured")
        self.assertTrue(result["wallet_impact"]["can_drain_tokens"])

    def test_successful_eth_call_is_neutral_observation(self):
        responses = ["0x6000", "0x", "0x5208"]
        with patch("scamshield.runtime.evm_simulation._rpc", new=AsyncMock(side_effect=responses)):
            result = asyncio.run(simulate_evm_transaction({"chainId": 1, "from": WALLET, "to": TOKEN, "data": "0x"}))
        self.assertEqual(result["status"], "observed")
        self.assertTrue(result["details"]["call"]["success"])
        self.assertEqual(result["evidence"][0]["severity"], 0)
        self.assertFalse(result["details"]["broadcast"])

    def test_revert_is_neutral_execution_result(self):
        error = RpcError("eth_call", {"message": "execution reverted", "data": "0x"})
        with patch("scamshield.runtime.evm_simulation._rpc", new=AsyncMock(side_effect=["0x6000", error, error])):
            result = asyncio.run(simulate_evm_transaction({"chainId": 1, "from": WALLET, "to": TOKEN, "data": "0xdeadbeef"}))
        self.assertEqual(result["status"], "reverted")
        self.assertFalse(result["details"]["call"]["success"])
        self.assertEqual(result["evidence"][0]["severity"], 0)

    def test_invalid_input_does_not_contact_rpc(self):
        with patch("scamshield.runtime.evm_simulation._rpc", new=AsyncMock()) as rpc:
            result = asyncio.run(simulate_evm_transaction({"chainId": 1, "to": "not-an-address", "data": "0x"}))
        self.assertEqual(result["status"], "invalid_input")
        rpc.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
