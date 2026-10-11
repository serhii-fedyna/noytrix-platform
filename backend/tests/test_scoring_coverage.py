import unittest

from scamshield.core.scoring import score_scan


class ScoringCoverageTests(unittest.TestCase):
    def test_zero_sources_is_not_safe(self):
        result = score_scan([], [], [], {}, internal_only=True)

        self.assertEqual(result["assessment_status"], "insufficient_data")
        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["normalized_level"], "unknown")
        self.assertEqual(result["score"], 0)

    def test_failed_sources_are_not_safe(self):
        result = score_scan(
            [{"name": "rpc", "status": "timeout", "evidence": []}],
            [],
            [],
            {},
            internal_only=True,
        )

        self.assertEqual(result["assessment_status"], "insufficient_data")
        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["source_coverage"]["failed"], 1)

    def test_clean_coverage_can_be_safe(self):
        result = score_scan(
            [{"name": "rpc", "status": "clean", "evidence": []}],
            [],
            [],
            {},
            internal_only=True,
        )

        self.assertEqual(result["assessment_status"], "available")
        self.assertEqual(result["level"], "safe")

    def test_confirmed_malicious_evidence_wins_during_partial_outage(self):
        result = score_scan(
            [
                {
                    "name": "noytrix_scam_database",
                    "status": "malicious",
                    "evidence": [
                        {
                            "code": "noytrix_scam_database_match",
                            "severity": 95,
                            "hard_evidence": True,
                        }
                    ],
                },
                {"name": "rpc", "status": "timeout", "evidence": []},
            ],
            [],
            [],
            {},
            internal_only=True,
        )

        self.assertEqual(result["assessment_status"], "partial")
        self.assertNotEqual(result["level"], "unknown")
        self.assertTrue(result["confirmed_red_flag"])

    def test_duplicate_provider_copies_do_not_stack_confirmed_score(self):
        evidence = {
            "code": "known_malicious_entity",
            "entity": "0xabc",
            "raw_ref": "case-1",
            "severity": 95,
            "hard_evidence": True,
        }
        one = score_scan(
            [{"name": "internal_a", "status": "malicious", "evidence": [evidence]}],
            [], [], {}, internal_only=True,
        )
        duplicate = score_scan(
            [
                {"name": "internal_a", "status": "malicious", "evidence": [evidence]},
                {"name": "internal_b", "status": "malicious", "evidence": [evidence]},
            ],
            [], [], {}, internal_only=True,
        )

        self.assertEqual(one["internal_score"], duplicate["internal_score"])
        self.assertEqual(len(duplicate["canonical_evidence"]), 1)

    def test_observed_chain_data_does_not_become_suspicious(self):
        result = score_scan(
            [{"name": "solana_rpc", "status": "observed", "evidence": []}],
            [], [], {}, internal_only=True,
        )
        self.assertEqual(result["level"], "safe")
        self.assertEqual(result["score"], 0)

    def test_high_brand_heuristic_is_not_hard_evidence(self):
        result = score_scan(
            [
                {
                    "name": "visual_phishing",
                    "status": "malicious",
                    "evidence": [{"code": "brand_spoofing", "severity": 95}],
                }
            ],
            [], [], {}, internal_only=True,
        )
        self.assertFalse(result["confirmed_red_flag"])
        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["assessment_status"], "partial")

    def test_confirmed_honeypot_simulation_drives_contract_risk(self):
        result = score_scan(
            [{
                "name": "honeypot",
                "status": "malicious",
                "evidence": [{
                    "code": "honeypot_detected",
                    "severity": 95,
                    "confidence": 95,
                    "confirmed": True,
                    "hard_evidence": True,
                    "method": "sell_simulation",
                }],
            }],
            [], [], {}, internal_only=True,
        )
        self.assertTrue(result["confirmed_red_flag"])
        self.assertIn(result["level"], {"danger", "critical"})

    def test_unconfirmed_honeypot_label_does_not_drive_risk(self):
        result = score_scan(
            [{
                "name": "honeypot",
                "status": "observed",
                "evidence": [{"code": "honeypot_simulation_incomplete", "severity": 0}],
            }],
            [], [], {}, internal_only=True,
        )
        self.assertFalse(result["confirmed_red_flag"])
        self.assertEqual(result["score"], 0)


if __name__ == "__main__":
    unittest.main()
