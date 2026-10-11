import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

if "httpx" not in sys.modules:
    class _Client:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
    stub = types.ModuleType("httpx")
    stub.AsyncClient = _Client
    stub.Timeout = lambda *args, **kwargs: None
    stub.TimeoutException = TimeoutError
    sys.modules["httpx"] = stub

from scamshield.intelligence.evm_rpc import _address_word, analyze_evm_contract, analyze_verified_abi


class EvmRpcTests(unittest.IsolatedAsyncioTestCase):
    def test_decodes_only_nonzero_address_words(self):
        self.assertEqual(_address_word("0x" + "0" * 24 + "1" * 40), "0x" + "1" * 40)
        self.assertIsNone(_address_word("0x" + "0" * 64))

    def test_verified_abi_privileges_are_structured_not_scored(self):
        result = analyze_verified_abi([
            {"type": "function", "name": "mint", "stateMutability": "nonpayable", "inputs": [{"type": "address"}, {"type": "uint256"}]},
            {"type": "function", "name": "setSellTax", "stateMutability": "nonpayable", "inputs": [{"type": "uint256"}]},
            {"type": "function", "name": "balanceOf", "stateMutability": "view", "inputs": [{"type": "address"}]},
        ])
        self.assertTrue(result["available"])
        self.assertEqual(result["function_count"], 3)
        self.assertEqual(result["privileged_functions"]["minting"][0]["name"], "mint")
        self.assertEqual(result["privileged_functions"]["fees"][0]["name"], "setSellTax")

    async def test_reads_proxy_and_owner_as_neutral_facts(self):
        words = {
            "eth_getCode": "0x60016000",
            "eth_getStorageAt": ["0x" + "0" * 24 + "2" * 40, "0x" + "0" * 24 + "3" * 40],
            "eth_call": ["0x" + "0" * 24 + "4" * 40, "0x" + "0" * 63 + "0"],
        }
        async def fake_rpc(_client, _endpoint, method, _params):
            value = words[method]
            return value.pop(0) if isinstance(value, list) else value
        with patch("scamshield.intelligence.evm_rpc._rpc", new=AsyncMock(side_effect=fake_rpc)):
            result = await analyze_evm_contract("0x" + "a" * 40, "1", "https://rpc.test")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["details"]["implementation"], "0x" + "2" * 40)
        self.assertEqual(result["details"]["proxy_admin"], "0x" + "3" * 40)
        self.assertEqual(result["details"]["owner"], "0x" + "4" * 40)
        self.assertTrue(all(item["severity"] == 0 for item in result["evidence"]))

    async def test_eoa_is_not_reported_safe(self):
        with patch("scamshield.intelligence.evm_rpc._rpc", new=AsyncMock(return_value="0x")):
            result = await analyze_evm_contract("0x" + "a" * 40, "1", "https://rpc.test")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["verdict"], "unknown")
        self.assertFalse(result["details"]["has_contract_code"])


if __name__ == "__main__":
    unittest.main()
