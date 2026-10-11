import unittest

from scamshield.ai.explainer import _insufficient_evidence_explanation, validate_ai_explanation_output


class AiExplainerFormattingTests(unittest.TestCase):
    def test_provider_markdown_is_removed_from_report_fields(self):
        explanation = validate_ai_explanation_output(
            {
                "short": "**Critical risk**: `100/100`.",
                "details": (
                    "## Why this matters\n"
                    "A fake **MetaMask** login page may request a recovery phrase."
                ),
                "risks": [
                    "- Recovery phrase theft",
                    "1. Malicious wallet connection",
                ],
                "actions": ["* Do not connect a wallet or enter a recovery phrase."],
                "confidence": "high",
                "needs_confirmation": False,
            },
            {"level": "critical", "score": 100},
            "detailed",
        )

        combined = " ".join(
            [
                explanation["short"],
                explanation["details"],
                *explanation["risks"],
                *explanation["actions"],
            ]
        )
        self.assertNotRegex(combined, r"\*\*|`|^[-*] |\b1\. ")
        self.assertIn("Critical risk: 100/100.", explanation["short"])
        self.assertIn("Recovery phrase theft", explanation["risks"])

    def test_unavailable_required_data_never_becomes_an_attack_story(self):
        result = _insufficient_evidence_explanation({
            "assessment_status": "insufficient_data",
            "confirmed_red_flag": False,
            "level": "unknown",
            "score": 0,
            "sources": [{"name": "solana_rpc", "status": "source_unavailable"}],
        }, "ru")

        self.assertIn("не завершена", result["short"].lower())
        self.assertNotIn("замороз", result["details"].lower())


if __name__ == "__main__":
    unittest.main()
