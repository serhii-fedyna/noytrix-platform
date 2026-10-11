import unittest

from scamshield.core.report_cards import REPORT_CARDS_SCHEMA_VERSION, build_report_cards


class ReportCardsTests(unittest.TestCase):
    def test_cards_are_built_from_known_coded_evidence_not_provider_text(self):
        report = build_report_cards(
            {
                "input": "bad.example",
                "level": "critical",
                "sources": [
                    {
                        "name": "noytrix_scam_database",
                        "status": "malicious",
                        "evidence": [
                            {
                                "code": "documented_incident_exact_match",
                                "severity": 95,
                                "confirmed": True,
                                "text": "untrusted provider prose must not be shown",
                            }
                        ],
                    }
                ],
            },
            "en",
        )

        self.assertEqual(report["schema_version"], REPORT_CARDS_SCHEMA_VERSION)
        self.assertEqual(len(report["evidence_cards"]), 1)
        self.assertEqual(report["evidence_cards"][0]["code"], "documented_incident_exact_match")
        self.assertNotIn("untrusted provider prose", report["evidence_cards"][0]["detail"])
        self.assertEqual(report["action_cards"][0]["id"], "action:1")

    def test_unknown_codes_are_not_rendered_as_customer_evidence(self):
        report = build_report_cards(
            {
                "level": "suspicious",
                "sources": [
                    {
                        "name": "experimental_detector",
                        "status": "malicious",
                        "evidence": [{"code": "new_unreviewed_signal", "severity": 99, "confirmed": True}],
                    }
                ],
            },
            "en",
        )
        self.assertEqual(report["evidence_cards"], [])
        self.assertEqual(report["check_cards"][0]["detector"], "experimental_detector")

    def test_missing_coverage_is_shown_as_a_limit_card(self):
        report = build_report_cards(
            {
                "level": "safe",
                "source_coverage": {"missing_capabilities": ["token_controls"]},
            },
            "uk",
        )
        self.assertEqual(report["limit_cards"][0]["id"], "coverage:missing")
        self.assertIn("недоступ", report["limit_cards"][0]["detail"].lower())

    def test_detector_aliases_keep_control_facts_distinct_from_scam_claims(self):
        report = build_report_cards(
            {
                "level": "suspicious",
                "sources": [{
                    "name": "solana_rpc",
                    "status": "observed",
                    "evidence": [{"code": "solana_freeze_authority_active", "severity": 25}],
                }],
            },
            "en",
        )
        self.assertEqual(report["evidence_cards"][0]["code"], "solana_freeze_authority_active")
        self.assertIn("not proof of a scam", report["evidence_cards"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
