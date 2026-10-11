import ast
import re
import unittest
from pathlib import Path
from typing import Tuple

from scamshield.url_intel.fusion import build_url_intelligence


def _load_brand_guard():
    source_path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8-sig"), filename=str(source_path))
    wanted_functions = {"_host_root_domain", "_looks_like_brand_spoof"}
    wanted_assignments = {"TRUSTED_BRANDS", "BRAND_SPOOF_HINTS"}
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            body.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in wanted_assignments
            for target in node.targets
        ):
            body.append(node)
    namespace = {"Tuple": Tuple, "re": re}
    module = ast.Module(body=body, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(source_path), "exec"), namespace)
    return namespace["_looks_like_brand_spoof"]


_looks_like_brand_spoof = _load_brand_guard()


class UrlFalsePositiveGuardTests(unittest.TestCase):
    def test_short_trusted_brand_does_not_match_normal_domain(self):
        matched, evidence = _looks_like_brand_spoof("example.com")
        self.assertFalse(matched)
        self.assertEqual(evidence, [])

    def test_real_brand_fragment_still_matches(self):
        matched, evidence = _looks_like_brand_spoof("binance-login.example")
        self.assertTrue(matched)
        self.assertTrue(evidence)

    def test_low_or_medium_memory_cannot_create_fresh_risk(self):
        result = build_url_intelligence(
            sources=[],
            heuristics=[],
            page_content=[],
            threat_memory={"score": 40, "level": "medium", "confidence": 90},
        )
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["level"], "safe")
        self.assertEqual(result["signals_count"], 0)

    def test_high_confidence_high_risk_memory_is_context_only(self):
        result = build_url_intelligence(
            sources=[],
            heuristics=[],
            page_content=[],
            threat_memory={"score": 90, "level": "critical", "confidence": 90},
        )
        self.assertEqual(result["score"], 20)
        self.assertEqual(result["level"], "low")
        self.assertTrue(result["only_memory_signal"])


if __name__ == "__main__":
    unittest.main()
