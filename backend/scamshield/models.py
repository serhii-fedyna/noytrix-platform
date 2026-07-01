from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Evidence:
    source: str
    code: str
    severity: int
    text: str


@dataclass
class SourceResult:
    name: str
    source: str
    status: str
    verdict: str
    details: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    status_text: str = ""


@dataclass
class CoreResult:
    ok: bool
    input: str
    normalized_input: str
    kind: str
    score: int
    level: str
    verdict_en: str
    verdict_ru: str
    verdict_localized: str
    confirmed_red_flag: bool
    malicious_sources: List[str]
    sources: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    details: Dict[str, Any] = field(default_factory=dict)
    community: Dict[str, Any] = field(default_factory=dict)
    scoring: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeResult:
    can_spend: bool = False
    unlimited: bool = False
    tokens: List[Dict[str, Any]] = field(default_factory=list)
    spend_limit: Optional[str] = None
    revoke_difficulty: str = "unknown"
    summary: str = ""
    spender: Optional[str] = None
    method: Optional[str] = None
    flags: List[str] = field(default_factory=list)


@dataclass
class UXResult:
    what_can_happen: str = ""
    worst_case: str = ""
    human_explanation: str = ""
    risk_reasons: List[str] = field(default_factory=list)
