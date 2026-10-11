import unittest

from tracking_intelligence import canonical_entity, extract_observations, typed_deltas


class TrackingIntelligenceTests(unittest.TestCase):
    def test_canonical_website(self):
        self.assertEqual(canonical_entity("https://www.noytrix.com/path", "url"), "website:noytrix.com")

    def test_extracts_typed_metrics(self):
        values = extract_observations({"provider": "rpc", "holder_count": 1000, "mint_authority": "A"}, "now")
        self.assertEqual({item["metric"] for item in values}, {"holder_count", "mint_authority"})

    def test_ignores_small_numeric_noise(self):
        before = extract_observations({"price_usd": 100}, "a")
        after = extract_observations({"price_usd": 105}, "b")
        self.assertEqual(typed_deltas(before, after), [])

    def test_detects_liquidity_removal(self):
        before = extract_observations({"liquidity_usd": 100000}, "a")
        after = extract_observations({"liquidity_usd": 50000}, "b")
        change = typed_deltas(before, after)[0]
        self.assertEqual(change["event_type"], "liquidity_usd_down")
        self.assertEqual(change["severity"], "high")

    def test_detects_authority_change(self):
        before = extract_observations({"freeze_authority": None}, "a")
        after = extract_observations({"freeze_authority": "new-authority"}, "b")
        added = typed_deltas(before, after)[0]
        self.assertEqual(added["event_type"], "freeze_authority_added")
        self.assertEqual(added["severity"], "critical")
        before = extract_observations({"freeze_authority": "old"}, "a")
        change = typed_deltas(before, after)[0]
        self.assertEqual(change["severity"], "critical")

    def test_observed_provider_values_are_compared(self):
        before = extract_observations({"source": "solana_rpc", "status": "observed", "holder_count": 1000}, "a")
        after = extract_observations({"source": "solana_rpc", "status": "observed", "holder_count": 1200}, "b")
        self.assertEqual(typed_deltas(before, after)[0]["event_type"], "holder_count_up")

    def test_provider_substitution_does_not_create_change(self):
        before = extract_observations({"source": "provider_a", "liquidity_usd": 100000}, "a")
        after = extract_observations({"source": "provider_b", "liquidity_usd": 50000}, "b")
        self.assertEqual(typed_deltas(before, after), [])

    def test_security_snapshot_wins_over_raw_provider_copy(self):
        values = extract_observations({
            "details": {"token": {"security_snapshot": {"market": {"liquidity_usd": 100000}}}},
            "raw": {"liquidity_usd": 1},
        }, "now")
        liquidity = next(item for item in values if item["metric"] == "liquidity_usd")
        self.assertEqual(liquidity["value"], 100000)


if __name__ == "__main__":
    unittest.main()
