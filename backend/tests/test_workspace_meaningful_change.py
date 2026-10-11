import ast
import re
import unittest
from pathlib import Path
from typing import Any

from tracking_intelligence import extract_observations, typed_deltas


def _load_change_functions():
    source_path = Path(__file__).resolve().parents[1] / "routes" / "workspace.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    wanted = {
        "_lang",
        "_safe_result",
        "_score_from_payload",
        "_level_from_payload",
        "_risk_rank",
        "_collect_risk_flags",
        "_meaningful_change",
    }
    module = ast.Module(
        body=[node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted],
        type_ignores=[],
    )
    namespace = {"Any": Any, "re": re, "extract_observations": extract_observations, "typed_deltas": typed_deltas}
    exec(compile(ast.fix_missing_locations(module), str(source_path), "exec"), namespace)
    return namespace["_safe_result"], namespace["_collect_risk_flags"], namespace["_meaningful_change"]


_safe_result, _collect_risk_flags, _meaningful_change = _load_change_functions()


class WorkspaceMeaningfulChangeTests(unittest.TestCase):
    def test_web_stream_never_exposes_generated_report_prose(self):
        streamed = _safe_result(
            {
                "risk_score": 95,
                "report": {"schema_version": "cards-v2"},
                "ai_explanation": "A long unverified narrative must never reach the web renderer.",
                "ai_explanation_result": {"text": "The same narrative in a nested legacy field."},
            }
        )

        self.assertEqual(streamed["report"]["schema_version"], "cards-v2")
        self.assertNotIn("ai_explanation", streamed)
        self.assertNotIn("ai_explanation_result", streamed)

    def test_neutral_field_names_and_text_do_not_create_risk_flags(self):
        payload = {
            "score": 0,
            "level": "safe",
            "details": {
                "holder_count": 1234,
                "honeypot_status": "checked; no honeypot detected",
                "malicious": False,
                "reputation": "No negative reputation was found",
            },
            "sources": [
                {
                    "name": "honeypot",
                    "verdict": "clean",
                    "evidence": [
                        {"code": "honeypot_checked", "severity": 0, "text": "No critical findings."}
                    ],
                }
            ],
        }

        self.assertEqual(_collect_risk_flags(payload), [])
        change = _meaningful_change({"score": 0, "level": "safe"}, payload)
        self.assertFalse(change["changed"])
        self.assertEqual(change["event_type"], "risk_status_stable")

    def test_new_positive_structured_evidence_creates_change(self):
        previous = {"score": 10, "level": "low", "evidence": []}
        current = {
            "score": 35,
            "level": "low",
            "evidence": [
                {"code": "suspicious_approval", "severity": 25, "text": "Unlimited approval detected."}
            ],
        }

        self.assertEqual(_collect_risk_flags(current), ["suspicious_approval"])
        change = _meaningful_change(previous, current)
        self.assertTrue(change["changed"])
        self.assertIn("suspicious_approval", change["summary"])

    def test_low_severity_evidence_does_not_wake_monitoring(self):
        previous = {"score": 5, "level": "low", "evidence": []}
        current = {
            "score": 8,
            "level": "low",
            "evidence": [{"code": "minor_metadata_warning", "severity": 10}],
        }

        self.assertEqual(_collect_risk_flags(current), [])
        self.assertFalse(_meaningful_change(previous, current)["changed"])

    def test_explicit_malicious_source_creates_change_without_text_search(self):
        previous = {"score": 0, "level": "safe", "malicious_sources": []}
        current = {
            "score": 0,
            "level": "safe",
            "malicious_sources": ["noytrix_scam_database"],
        }

        self.assertEqual(_collect_risk_flags(current), ["source:noytrix_scam_database"])
        self.assertTrue(_meaningful_change(previous, current)["changed"])

    def test_existing_signal_does_not_repeat_on_identical_snapshot(self):
        snapshot = {
            "score": 80,
            "level": "high",
            "evidence": [{"code": "phishing_match", "severity": 45, "hard_evidence": True}],
        }

        change = _meaningful_change(snapshot, snapshot)
        self.assertFalse(change["changed"])
        self.assertEqual(change["event_type"], "risk_status_stable")

    def test_metric_severity_controls_alert_severity(self):
        previous = {"score": 0, "level": "safe", "details": {"source": "evm_rpc", "status": "observed", "implementation": "0x1"}}
        current = {"score": 0, "level": "safe", "details": {"source": "evm_rpc", "status": "observed", "implementation": "0x2"}}
        change = _meaningful_change(previous, current)
        self.assertTrue(change["changed"])
        self.assertEqual(change["severity"], "critical")


if __name__ == "__main__":
    unittest.main()
