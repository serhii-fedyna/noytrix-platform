import unittest

from scamshield.intelligence.wallet_graph import build_directional_graph, select_expansion_nodes


class WalletGraphTests(unittest.TestCase):
    def test_failed_transfer_is_not_successful_flow(self):
        root = "0xroot"
        bad = "0xbad"
        graph = build_directional_graph(root, {root: {"events": [{"from": root, "to": bad, "event_type": "token", "failed": True, "amount": 10, "asset": "X"}]}}, {bad: {"confirmed_behaviors": ["stealing_attack"], "status": "malicious"}})
        self.assertEqual(graph["edges"][0]["successful_count"], 0)
        self.assertEqual(graph["dangerous_outgoing"], [])

    def test_incoming_malicious_transfer_does_not_accuse_root(self):
        root = "0xroot"
        bad = "0xbad"
        graph = build_directional_graph(root, {root: {"events": [{"from": bad, "to": root, "event_type": "token", "failed": False, "amount": 1, "asset": "SPAM"}]}}, {bad: {"confirmed_behaviors": ["phishing_activities"], "status": "malicious"}})
        self.assertEqual(len(graph["dangerous_incoming"]), 1)
        self.assertEqual(graph["verdict_policy"]["incoming_malicious_contact"], "context_only")

    def test_repeated_outgoing_counterparty_is_expanded_first(self):
        root = "0xroot"
        events = [
            {"from": root, "to": "0xa", "event_type": "normal", "failed": False},
            {"from": root, "to": "0xa", "event_type": "token", "failed": False},
            {"from": "0xb", "to": root, "event_type": "normal", "failed": False},
        ]
        self.assertEqual(select_expansion_nodes(root, {"events": events}, 1), ["0xa"])

    def test_edges_keep_asset_contracts_separate(self):
        root = "0xroot"
        history = {"events": [
            {"from": root, "to": "0xa", "event_type": "token", "asset_contract": "0x1", "failed": False, "amount": 2},
            {"from": root, "to": "0xa", "event_type": "token", "asset_contract": "0x2", "failed": False, "amount": 3},
        ]}
        graph = build_directional_graph(root, {root: history})
        self.assertEqual(graph["edge_count"], 2)

    def test_finds_two_hop_path_to_confirmed_malicious_node(self):
        root = "0xroot"
        middle = "0xmiddle"
        bad = "0xbad"
        histories = {
            root: {"events": [{"from": root, "to": middle, "event_type": "normal", "failed": False}]},
            middle: {"events": [{"from": middle, "to": bad, "event_type": "token", "failed": False}]},
        }
        graph = build_directional_graph(root, histories, {bad: {"confirmed_behaviors": ["stealing_attack"]}})
        self.assertEqual(graph["paths_to_confirmed_malicious"][0]["depth"], 2)
        self.assertEqual(graph["verdict_policy"]["two_hop_malicious_path"], "exposure_context_not_wallet_accusation")

    def test_flow_shape_is_neutral_context(self):
        root = "0xroot"
        events = [{"from": root, "to": f"0x{i}", "event_type": "normal", "failed": False} for i in range(10)]
        graph = build_directional_graph(root, {root: {"events": events}})
        self.assertEqual(graph["flow_patterns"]["fan_out_nodes"][0]["address"], root)
        self.assertIn("do not prove", graph["flow_patterns"]["interpretation"])


if __name__ == "__main__":
    unittest.main()
