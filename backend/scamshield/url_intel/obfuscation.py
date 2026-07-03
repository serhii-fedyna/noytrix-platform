from __future__ import annotations

import math
import re
from typing import Any, Dict, List


SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.I | re.S)
SRC_RE = re.compile(r"<script\b[^>]+src=[\"']([^\"']+)[\"']", re.I)


def _entropy(text: str) -> float:
    text = str(text or "")
    if not text:
        return 0.0
    counts = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(text)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _script_blobs(html: str) -> List[str]:
    html = str(html or "")
    blobs = [x.strip() for x in SCRIPT_RE.findall(html) if x and x.strip()]
    inline_handlers = re.findall(r"\bon\w+\s*=\s*[\"']([^\"']{40,})[\"']", html, flags=re.I)
    blobs.extend(x.strip() for x in inline_handlers if x and x.strip())
    return blobs[:80]


def _add(signals: List[Dict[str, Any]], code: str, severity: int, text: str, **extra: Any) -> None:
    item = {
        "code": code,
        "severity": max(0, min(100, int(severity))),
        "text": text,
    }
    item.update(extra)
    signals.append(item)


def _level(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "safe"


def analyze_obfuscated_javascript(html: str, runtime: Dict[str, Any] | None = None) -> Dict[str, Any]:
    html = str(html or "")
    runtime = runtime or {}
    scripts = _script_blobs(html)
    srcs = SRC_RE.findall(html)
    joined = "\n".join(scripts)
    low = joined.lower()
    signals: List[Dict[str, Any]] = []

    eval_hits = len(re.findall(r"\b(eval|function\s*\(|settimeout|setinterval)\s*\(", low))
    if eval_hits:
        _add(signals, "js_dynamic_eval_execution", min(72, 45 + eval_hits * 10), "JavaScript uses dynamic code execution primitives.", count=eval_hits)

    if re.search(r"eval\s*\(\s*function\s*\(\s*p\s*,\s*a\s*,\s*c\s*,\s*k\s*,\s*e\s*,\s*d", low):
        _add(signals, "js_packer_obfuscation", 88, "JavaScript resembles Dean Edwards / packer-style obfuscation.")

    base64_hits = re.findall(r"[A-Za-z0-9+/]{80,}={0,2}", joined)
    if base64_hits:
        _add(signals, "js_large_base64_blob", min(45, 20 + len(base64_hits) * 6), "JavaScript contains large base64-like encoded blobs.", count=len(base64_hits))

    hex_escape_hits = len(re.findall(r"(?:\\x[0-9a-fA-F]{2}){8,}", joined))
    unicode_escape_hits = len(re.findall(r"(?:\\u[0-9a-fA-F]{4}){6,}", joined))
    if hex_escape_hits or unicode_escape_hits:
        _add(
            signals,
            "js_escape_encoded_payload",
            min(86, 45 + (hex_escape_hits + unicode_escape_hits) * 10),
            "JavaScript contains dense escaped string payloads.",
            hex_count=hex_escape_hits,
            unicode_count=unicode_escape_hits,
        )

    string_array_hits = len(re.findall(r"\[[\"'][^\"']{2,}[\"'](?:\s*,\s*[\"'][^\"']{2,}[\"']){20,}\]", joined))
    if string_array_hits:
        _add(signals, "js_string_array_obfuscation", 76, "JavaScript uses large string arrays commonly seen in obfuscated loaders.", count=string_array_hits)

    computed_access_hits = len(re.findall(r"\[[\"'][a-zA-Z_$][\w$]{2,}[\"']\]", joined))
    if computed_access_hits >= 25:
        _add(signals, "js_computed_property_heavy", 50, "JavaScript heavily uses computed property access.", count=computed_access_hits)

    atob_hits = len(re.findall(r"\b(atob|btoa|fromcharcode|charcodeat|decodeuricomponent|unescape)\s*\(", low))
    if atob_hits >= 2:
        _add(signals, "js_decode_chain", min(75, 35 + atob_hits * 8), "JavaScript uses repeated decode/deobfuscation helpers.", count=atob_hits)

    import_hits = len(re.findall(r"\b(import\s*\(|new\s+function|document\.createelement\s*\(\s*[\"']script)", low))
    if import_hits:
        _add(signals, "js_dynamic_script_loading", min(70, 35 + import_hits * 8), "JavaScript dynamically loads or creates script code.", count=import_hits)

    long_line_count = sum(1 for line in joined.splitlines() if len(line) >= 1200)
    if long_line_count:
        _add(signals, "js_minified_or_packed_long_lines", min(58, 25 + long_line_count * 5), "JavaScript contains very long packed/minified lines.", count=long_line_count)

    if scripts:
        entropies = [_entropy(s[:12000]) for s in scripts if len(s) >= 500]
        max_entropy = max(entropies or [0.0])
        if max_entropy >= 5.15 and len(joined) >= 2000:
            _add(signals, "js_high_entropy_payload", 62, "JavaScript has high-entropy payloads consistent with encoded code.", entropy=round(max_entropy, 3))

    wallet_terms = any(x in low for x in [
        "ethereum.request",
        "eth_sendtransaction",
        "eth_signtypeddata",
        "personal_sign",
        "permit2",
        "setapprovalforall",
        "transferfrom",
        "approve(",
    ])
    obfuscated = any(int(x.get("severity") or 0) >= 35 for x in signals)
    if wallet_terms and obfuscated:
        _add(signals, "obfuscated_wallet_drainer_javascript", 94, "Obfuscated JavaScript also references wallet signing or asset movement behavior.")

    runtime_wallet_calls = runtime.get("wallet_calls") or []
    if runtime_wallet_calls and obfuscated:
        _add(signals, "runtime_wallet_calls_with_obfuscation", 90, "Runtime wallet calls were observed on a page with obfuscated JavaScript.")

    third_party_scripts = [s for s in srcs if not s.startswith("/") and not s.startswith("./")]
    if len(third_party_scripts) >= 15 and obfuscated:
        _add(signals, "many_external_scripts_with_obfuscation", 64, "Page combines many external scripts with obfuscated inline code.", count=len(third_party_scripts))

    score = max([int(s.get("severity") or 0) for s in signals] or [0])

    return {
        "available": True,
        "score": score,
        "level": _level(score),
        "signals": sorted(signals, key=lambda x: int(x.get("severity") or 0), reverse=True)[:30],
        "metrics": {
            "inline_script_count": len(scripts),
            "external_script_count": len(srcs),
            "script_bytes": len(joined),
            "max_entropy": max([_entropy(s[:12000]) for s in scripts if len(s) >= 500] or [0.0]),
        },
        "summary": (
            "Obfuscated wallet-drainer JavaScript detected."
            if score >= 90 else
            "Obfuscated JavaScript risk signals detected."
            if score >= 60 else
            "No strong obfuscated JavaScript risk detected."
        ),
    }
