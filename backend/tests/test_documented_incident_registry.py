import unittest

from scamshield.intelligence.noytrix_scam_database import lookup_noytrix_scam_database


LIBRA_MINT = "Bo9jh3wsmcC2AjakLWzNmKJ3SgtZmXEcSaW7L2FAvUsU"
HAWK_MINT = "HAWKThXRcNL9ZGZKqgUXLm4W8tnRZ7U6MVdEepSutj34"


class DocumentedIncidentRegistryTests(unittest.TestCase):
    def test_reviewed_solana_incident_is_an_exact_high_confidence_match(self):
        result = lookup_noytrix_scam_database(LIBRA_MINT)

        self.assertTrue(result["matched"])
        self.assertTrue(result["force_verdict"])
        self.assertEqual(result["source"], "documented_incident_registry")
        self.assertEqual(result["status"], "critical")
        self.assertGreaterEqual(result["risk_score"], 90)
        self.assertGreaterEqual(len(result["metadata"]["sources"]), 2)
        self.assertEqual(result["metadata"]["classification"], "documented_rug_pull")

    def test_unrelated_solana_mint_is_not_matched_by_the_incident_registry(self):
        result = lookup_noytrix_scam_database("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

        self.assertFalse(result["matched"])

    def test_hawk_is_a_source_backed_historical_incident_not_an_unexplained_exception(self):
        result = lookup_noytrix_scam_database(HAWK_MINT)

        self.assertTrue(result["matched"])
        self.assertTrue(result["force_verdict"])
        self.assertEqual(result["source"], "documented_incident_registry")
        self.assertEqual(result["status"], "critical")
        self.assertGreaterEqual(result["risk_score"], 90)
        self.assertEqual(result["metadata"]["classification"], "documented_high_risk_incident")
        self.assertGreaterEqual(len(result["metadata"]["sources"]), 3)


if __name__ == "__main__":
    unittest.main()
