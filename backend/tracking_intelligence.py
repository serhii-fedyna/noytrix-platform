from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from scamshield.core.entities import canonical_entity_id, resolve_input_syntax


METRICS = {
    "price_usd": ({"price_usd", "priceusd", "price"}, "usd", 0.10),
    "market_cap_usd": ({"market_cap", "marketcap", "market_cap_usd"}, "usd", 0.15),
    "fdv_usd": ({"fdv", "fully_diluted_valuation"}, "usd", 0.15),
    "liquidity_usd": ({"liquidity", "liquidity_usd", "liquidityusd"}, "usd", 0.20),
    "volume_24h_usd": ({"volume_24h", "volume24h", "volume_h24"}, "usd", 0.50),
    "holder_count": ({"holder_count", "holders", "holders_count"}, "count", 0.05),
    "top_holder_concentration_pct": ({"top_holder_concentration", "top10_percentage", "top_10_holders_percentage"}, "percent", 0.05),
    "supply": ({"supply", "total_supply", "circulating_supply"}, "token", 0.01),
    "balance_usd": ({"balance_usd", "portfolio_value_usd", "net_worth_usd"}, "usd", 0.10),
    "transaction_count": ({"transaction_count", "tx_count", "transactions_count"}, "count", 0.05),
    "buy_tax_pct": ({"buy_tax", "buy_tax_pct"}, "percent", 0.01),
    "sell_tax_pct": ({"sell_tax", "sell_tax_pct"}, "percent", 0.01),
}

STATE_METRICS = {
    "mint_authority": {"mint_authority", "mintauthority"},
    "freeze_authority": {"freeze_authority", "freezeauthority"},
    "update_authority": {"update_authority", "updateauthority", "metadata_authority"},
    "contract_owner": {"contract_owner", "owner_address", "contractowner"},
    "proxy_implementation": {"proxy_implementation", "implementation_address", "implementation"},
    "sellability": {"sellability", "can_sell", "is_honeypot"},
    "dns_nameservers": {"nameservers", "name_servers", "dns_nameservers"},
    "ssl_fingerprint": {"ssl_fingerprint", "certificate_fingerprint", "cert_fingerprint"},
    "whois_registrar": {"registrar", "whois_registrar"},
    "html_hash": {"html_hash", "dom_hash"},
    "javascript_hash": {"javascript_hash", "js_hash", "script_hash"},
    "redirect_chain": {"redirect_chain", "redirects"},
    "token_2022_extensions": {"token_2022_extensions", "extensions"},
    "account_owner": {"account_owner", "program_owner"},
}

USABLE_STATUSES = {"available", "clean", "observed", "suspicious", "malicious"}

MIN_ABSOLUTE_CHANGE = {
    "price_usd": 0.000001,
    "market_cap_usd": 50_000.0,
    "fdv_usd": 50_000.0,
    "liquidity_usd": 10_000.0,
    "volume_24h_usd": 10_000.0,
    "holder_count": 10.0,
    "top_holder_concentration_pct": 2.0,
    "supply": 1.0,
    "balance_usd": 100.0,
    "transaction_count": 5.0,
    "buy_tax_pct": 1.0,
    "sell_tax_pct": 1.0,
}


def canonical_entity(target: str, kind: str | None = None, network: str | None = None) -> str:
    resolution = resolve_input_syntax(target)
    explicit_kind = str(kind or "").lower().strip()
    resolved_type = explicit_kind if explicit_kind in {"wallet", "contract", "token", "program", "account", "website"} else None
    return canonical_entity_id(resolution, resolved_type=resolved_type, network=network)


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").replace("$", "").replace("%", "").strip())
        return number if abs(number) < 1e30 else None
    except (TypeError, ValueError):
        return None


def _meaningful_state(value: Any) -> bool:
    """Reject empty provider payloads before they can become a fake change.

    Some providers return a shaped object whose fields are all null.  Serialising
    it makes a different JSON string on later checks even though no security
    fact changed.  Such payloads must not become user-facing events.
    """
    if value is None or value == "":
        return False
    if isinstance(value, dict):
        return any(_meaningful_state(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_meaningful_state(item) for item in value)
    return True


def extract_observations(payload: dict[str, Any], observed_at: str | None = None) -> list[dict[str, Any]]:
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    found: dict[str, dict[str, Any]] = {}
    numeric_lookup = {alias: (metric, unit, threshold) for metric, (aliases, unit, threshold) in METRICS.items() for alias in aliases}
    state_lookup = {alias: metric for metric, aliases in STATE_METRICS.items() for alias in aliases}

    def store(metric: str, observation: dict[str, Any], path: tuple[str, ...]) -> None:
        path_text = ".".join(path).lower()
        path_rank = (
            50 if "security_snapshot" in path_text else
            40 if "canonical_evidence" in path_text else
            30 if "details" in path_text else
            20 if "sources" in path_text else
            -10 if "raw" in path_text else 10
        )
        status_rank = 10 if observation.get("status") in USABLE_STATUSES else 0
        confidence_rank = observation.get("confidence") or 0
        quality = (path_rank + status_rank, confidence_rank, str(observation.get("source") or ""))
        current = found.get(metric)
        if current is None or quality > current.get("_quality", (-999, -999, "")):
            observation["path"] = ".".join(path)
            observation["_quality"] = quality
            found[metric] = observation

    def visit(value: Any, source: str = "scan_core", inherited_status: str = "available", path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            local_source = str(value.get("source") or value.get("provider") or source)[:80]
            status = str(value.get("status") or inherited_status or "available").lower()
            confidence = _number(value.get("confidence"))
            for key, item in value.items():
                normalized = _key(key)
                if normalized in numeric_lookup:
                    metric, unit, _ = numeric_lookup[normalized]
                    number = _number(item)
                    if number is not None:
                        store(metric, {"metric": metric, "value": number, "unit": unit, "source": local_source, "status": status, "confidence": confidence, "observed_at": timestamp}, path + (str(key),))
                elif normalized in state_lookup:
                    metric = state_lookup[normalized]
                    if not _meaningful_state(item):
                        continue
                    stable = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, (dict, list)) else None if item is None else str(item)
                    store(metric, {"metric": metric, "value": stable, "unit": "state", "source": local_source, "status": status, "confidence": confidence, "observed_at": timestamp}, path + (str(key),))
                visit(item, local_source, status, path + (str(key),))
        elif isinstance(value, list):
            for index, item in enumerate(value[:500]):
                visit(item, source, inherited_status, path + (str(index),))

    visit(payload)
    output = []
    for item in found.values():
        clean = dict(item)
        clean.pop("_quality", None)
        output.append(clean)
    return sorted(output, key=lambda item: item["metric"])


def typed_deltas(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    before = {item["metric"]: item for item in previous if item.get("status") in USABLE_STATUSES}
    after = {item["metric"]: item for item in current if item.get("status") in USABLE_STATUSES}
    changes: list[dict[str, Any]] = []
    for metric, new in after.items():
        old = before.get(metric)
        if not old or old.get("value") == new.get("value"):
            continue
        if str(old.get("source") or "") != str(new.get("source") or ""):
            # A provider substitution is not an object change. It becomes
            # comparable after the next observation from the same provider.
            continue
        if metric in METRICS:
            old_number, new_number = _number(old.get("value")), _number(new.get("value"))
            if old_number is None or new_number is None:
                continue
            relative = abs(new_number - old_number) / max(abs(old_number), 1e-12)
            absolute = abs(new_number - old_number)
            threshold = METRICS[metric][2]
            if relative < threshold or absolute < MIN_ABSOLUTE_CHANGE.get(metric, 0.0):
                continue
            severity = "high" if metric == "liquidity_usd" and new_number < old_number and relative >= 0.40 else "medium"
            changes.append({"metric": metric, "event_type": f"{metric}_{'down' if new_number < old_number else 'up'}", "previous": old_number, "current": new_number, "absolute_change": round(absolute, 8), "relative_change": round(relative, 6), "severity": severity, "source": new.get("source"), "observed_at": new.get("observed_at")})
        else:
            removed = old.get("value") not in {None, "", "null"} and new.get("value") in {None, "", "null"}
            severity = "low" if removed and metric in {"mint_authority", "freeze_authority"} else "critical" if metric in {"mint_authority", "freeze_authority", "proxy_implementation", "contract_owner", "sellability"} else "high"
            event_suffix = "removed" if removed else "added" if old.get("value") in {None, "", "null"} else "changed"
            changes.append({"metric": metric, "event_type": f"{metric}_{event_suffix}", "previous": old.get("value"), "current": new.get("value"), "severity": severity, "source": new.get("source"), "observed_at": new.get("observed_at")})
    return sorted(changes, key=lambda item: {"critical": 3, "high": 2, "medium": 1}.get(item["severity"], 0), reverse=True)
