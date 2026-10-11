import unittest

from scamshield.core.evidence import (
    actionable_risk_evidence,
    canonical_evidence,
    evidence_from_sources,
)


class EvidenceContractTests(unittest.TestCase):
    def test_rejects_unstructured_text_without_code(self):
        self.assertIsNone(
            canonical_evidence(
                {"text": "holder honeypot malicious"},
                source="provider",
                source_status="malicious",
            )
        )

    def test_neutral_check_is_not_actionable_risk(self):
        evidence = evidence_from_sources(
            [
                {
                    "name": "honeypot",
                    "status": "clean",
                    "evidence": [{"code": "honeypot_checked", "severity": 0}],
                }
            ]
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["polarity"], "neutral")
        self.assertEqual(actionable_risk_evidence(evidence), [])

    def test_duplicate_fact_is_counted_once_with_corroboration(self):
        evidence = evidence_from_sources(
            [
                {
                    "name": "feed_a",
                    "status": "malicious",
                    "evidence": [
                        {
                            "code": "known_malicious_entity",
                            "entity": "0xabc",
                            "raw_ref": "case-1",
                            "severity": 90,
                            "hard_evidence": True,
                        }
                    ],
                },
                {
                    "name": "feed_b",
                    "status": "malicious",
                    "evidence": [
                        {
                            "code": "known_malicious_entity",
                            "entity": "0xabc",
                            "raw_ref": "case-1",
                            "severity": 95,
                            "hard_evidence": True,
                        }
                    ],
                },
            ]
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["corroboration_count"], 2)
        self.assertEqual(evidence[0]["corroborating_sources"], ["feed_a", "feed_b"])
        self.assertEqual(evidence[0]["severity"], 95)

    def test_source_must_be_malicious_for_actionable_risk(self):
        evidence = evidence_from_sources(
            [
                {
                    "name": "provider",
                    "status": "clean",
                    "evidence": [
                        {"code": "match", "severity": 95, "hard_evidence": True}
                    ],
                }
            ]
        )
        self.assertEqual(actionable_risk_evidence(evidence), [])

    def test_expired_evidence_cannot_drive_current_risk(self):
        evidence = evidence_from_sources(
            [
                {
                    "name": "provider",
                    "status": "malicious",
                    "fresh_until": "2020-01-01T00:00:00Z",
                    "evidence": [
                        {"code": "known_malicious_entity", "severity": 95, "hard_evidence": True}
                    ],
                }
            ]
        )
        self.assertEqual(actionable_risk_evidence(evidence), [])

    def test_future_freshness_keeps_evidence_actionable(self):
        item = canonical_evidence(
            {
                "code": "known_malicious_entity",
                "severity": 95,
                "hard_evidence": True,
                "fresh_until": "2099-01-01T00:00:00Z",
            },
            source="provider",
            source_status="malicious",
        )
        self.assertEqual(len(actionable_risk_evidence([item])), 1)


if __name__ == "__main__":
    unittest.main()
