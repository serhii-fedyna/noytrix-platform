import unittest

from scamshield.intelligence.evm_history import summarize_evm_history


class EvmHistoryTests(unittest.TestCase):
    def test_summarizes_distinct_history_types_without_claiming_completeness(self):
        wallet = "0x" + "a" * 40
        other = "0x" + "b" * 40
        token = "0x" + "c" * 40
        result = summarize_evm_history(
            wallet,
            {"result": [{"from": wallet, "to": other, "timeStamp": "100", "isError": "0"}]},
            {"result": [{"from": other, "to": wallet, "timeStamp": "110", "isError": "1"}]},
            {"result": [{"from": other, "to": wallet, "contractAddress": token, "timeStamp": "120"}]},
            {"result": []},
        )
        self.assertEqual(result["normal_transactions"], 1)
        self.assertEqual(result["internal_transfers"], 1)
        self.assertEqual(result["token_transfers"], 1)
        self.assertEqual(result["incoming_events"], 2)
        self.assertEqual(result["outgoing_events"], 1)
        self.assertEqual(result["failed_events"], 1)
        self.assertIn(token, result["token_contracts"])
        self.assertFalse(result["sample_complete"])
        self.assertEqual(result["events"][0]["direction"], "outgoing")
        self.assertEqual(result["events"][1]["direction"], "incoming")

    def test_error_message_is_not_mistaken_for_history(self):
        result = summarize_evm_history("0xabc", {"result": "No transactions found"}, {}, {}, {})
        self.assertFalse(result["history_found"])
        self.assertEqual(result["sampled_events"], 0)


if __name__ == "__main__":
    unittest.main()
