from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from scamshield.intelligence.evm_history import fetch_evm_history
from scamshield.intelligence.wallet_exposure import check_address_reputation


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def build_directional_graph(root: str, histories: dict[str, dict[str, Any]], reputations: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    root = root.lower()
    reputations = reputations or {}
    edge_groups: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    node_activity: dict[str, dict[str, int]] = defaultdict(lambda: {"incoming": 0, "outgoing": 0, "failed": 0})
    raw_event_count = 0
    for observed_address, history in histories.items():
        for event in (history or {}).get("events") or []:
            sender = str(event.get("from") or "").lower()
            recipient = str(event.get("to") or "").lower()
            if not sender or not recipient or sender == ZERO_ADDRESS or recipient == ZERO_ADDRESS:
                continue
            raw_event_count += 1
            asset_type = str(event.get("event_type") or "unknown")
            contract = str(event.get("asset_contract") or "").lower() or None
            key = (sender, recipient, asset_type, contract)
            group = edge_groups.setdefault(key, {
                "from": sender, "to": recipient, "event_type": asset_type,
                "asset_contract": contract, "asset": event.get("asset"),
                "event_count": 0, "successful_count": 0, "failed_count": 0,
                "amount_total": 0.0, "amount_known_count": 0,
                "first_seen": event.get("timestamp"), "last_seen": event.get("timestamp"),
                "transaction_samples": [], "observed_from": [],
            })
            group["event_count"] += 1
            if event.get("failed"):
                group["failed_count"] += 1
            else:
                group["successful_count"] += 1
            if event.get("amount") is not None:
                group["amount_total"] += float(event["amount"])
                group["amount_known_count"] += 1
            timestamp = event.get("timestamp")
            if timestamp:
                group["first_seen"] = min(filter(None, [group.get("first_seen"), timestamp]))
                group["last_seen"] = max(filter(None, [group.get("last_seen"), timestamp]))
            if event.get("transaction_hash") and event["transaction_hash"] not in group["transaction_samples"] and len(group["transaction_samples"]) < 5:
                group["transaction_samples"].append(event["transaction_hash"])
            if observed_address not in group["observed_from"]:
                group["observed_from"].append(observed_address)
            node_activity[sender]["outgoing"] += 1
            node_activity[recipient]["incoming"] += 1
            if event.get("failed"):
                node_activity[sender]["failed"] += 1

    addresses = {root}
    for edge in edge_groups.values():
        addresses.update((edge["from"], edge["to"]))
    nodes = []
    for address in sorted(addresses):
        reputation = reputations.get(address) or {}
        nodes.append({
            "address": address,
            "is_root": address == root,
            "incoming_events": node_activity[address]["incoming"],
            "outgoing_events": node_activity[address]["outgoing"],
            "failed_outgoing_events": node_activity[address]["failed"],
            "reputation_status": reputation.get("status") or "unknown",
            "confirmed_behaviors": reputation.get("confirmed_behaviors") or [],
            "all_behaviors": reputation.get("behaviors") or [],
            "classification": reputation.get("classification") or [],
        })
    edges = sorted(edge_groups.values(), key=lambda row: (row["event_count"], row["last_seen"] or ""), reverse=True)
    direct_outgoing = [edge for edge in edges if edge["from"] == root and edge["successful_count"] > 0]
    direct_incoming = [edge for edge in edges if edge["to"] == root and edge["successful_count"] > 0]
    dangerous_outgoing = [edge for edge in direct_outgoing if (reputations.get(edge["to"]) or {}).get("confirmed_behaviors")]
    dangerous_incoming = [edge for edge in direct_incoming if (reputations.get(edge["from"]) or {}).get("confirmed_behaviors")]
    successful_edges = [edge for edge in edges if edge["successful_count"] > 0]
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in successful_edges:
        adjacency[edge["from"]].append(edge)
    risk_paths: list[dict[str, Any]] = []
    for first in adjacency.get(root, []):
        first_target = first["to"]
        first_rep = reputations.get(first_target) or {}
        if first_rep.get("confirmed_behaviors"):
            risk_paths.append({"depth": 1, "addresses": [root, first_target], "behaviors": first_rep.get("confirmed_behaviors"), "edges": [first]})
        for second in adjacency.get(first_target, []):
            second_target = second["to"]
            second_rep = reputations.get(second_target) or {}
            if second_target != root and second_rep.get("confirmed_behaviors"):
                risk_paths.append({"depth": 2, "addresses": [root, first_target, second_target], "behaviors": second_rep.get("confirmed_behaviors"), "edges": [first, second]})
    outgoing_degree = defaultdict(int)
    incoming_degree = defaultdict(int)
    edge_pairs = set()
    for edge in successful_edges:
        outgoing_degree[edge["from"]] += 1
        incoming_degree[edge["to"]] += 1
        edge_pairs.add((edge["from"], edge["to"]))
    cycles = sorted({tuple(sorted((left, right))) for left, right in edge_pairs if (right, left) in edge_pairs and left != right})
    patterns = {
        "fan_out_nodes": [{"address": address, "distinct_outgoing_edges": count} for address, count in outgoing_degree.items() if count >= 10],
        "aggregation_nodes": [{"address": address, "distinct_incoming_edges": count} for address, count in incoming_degree.items() if count >= 10],
        "bidirectional_pairs": [{"addresses": list(pair)} for pair in cycles],
        "repeated_relationship_count": sum(1 for edge in successful_edges if edge["event_count"] >= 2),
        "interpretation": "Flow shape is descriptive context. Fan-out aggregation cycles and repetition do not prove illicit activity.",
    }
    return {
        "root": root, "nodes": nodes, "edges": edges,
        "node_count": len(nodes), "edge_count": len(edges), "raw_event_count": raw_event_count,
        "direct_outgoing_edge_count": len(direct_outgoing), "direct_incoming_edge_count": len(direct_incoming),
        "repeated_edges": [edge for edge in edges if edge["event_count"] >= 2],
        "dangerous_outgoing": dangerous_outgoing,
        "dangerous_incoming": dangerous_incoming,
        "paths_to_confirmed_malicious": risk_paths,
        "flow_patterns": patterns,
        "verdict_policy": {
            "incoming_malicious_contact": "context_only",
            "outgoing_malicious_contact": "exposure_warning_not_wallet_accusation",
            "failed_transactions": "excluded_from_successful_money_flow",
            "two_hop_malicious_path": "exposure_context_not_wallet_accusation",
            "flow_shape": "context_only_without_independent_evidence",
        },
    }


def select_expansion_nodes(root: str, history: dict[str, Any], limit: int = 3) -> list[str]:
    scores: dict[str, int] = defaultdict(int)
    root = root.lower()
    for event in (history or {}).get("events") or []:
        if event.get("failed"):
            continue
        sender = str(event.get("from") or "").lower()
        recipient = str(event.get("to") or "").lower()
        counterparty = recipient if sender == root else sender if recipient == root else ""
        if not counterparty or counterparty == ZERO_ADDRESS:
            continue
        scores[counterparty] += 4 if sender == root else 1
        if event.get("event_type") in {"token", "nft"}:
            scores[counterparty] += 1
    return [address for address, _score in sorted(scores.items(), key=lambda row: (row[1], row[0]), reverse=True)[:limit]]


async def investigate_wallet_graph(root: str, chain_id: str, api_key: str, base: str, root_history: dict[str, Any], expansion_limit: int = 3) -> dict[str, Any]:
    import httpx

    expansion = select_expansion_nodes(root, root_history, expansion_limit)
    histories = {root.lower(): root_history}
    failed_expansions: list[str] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(18.0, connect=6.0)) as client:
        results = await asyncio.gather(*[fetch_evm_history(client, base, chain_id, address, api_key) for address in expansion], return_exceptions=True)
    for address, result in zip(expansion, results):
        if isinstance(result, Exception):
            failed_expansions.append(address)
        else:
            histories[address] = result
    all_addresses = {root.lower()}
    for history in histories.values():
        for event in history.get("events") or []:
            all_addresses.update(str(event.get(key) or "").lower() for key in ("from", "to") if event.get(key))
    reputation_targets = list(dict.fromkeys(expansion + [item for item in all_addresses if item != root.lower()]))[:20]
    semaphore = asyncio.Semaphore(6)
    async def reputation(address: str) -> dict[str, Any]:
        async with semaphore:
            return await check_address_reputation(address, chain_id)
    reputation_rows = await asyncio.gather(*[reputation(address) for address in reputation_targets])
    reputations = {row["address"].lower(): row for row in reputation_rows if row.get("address")}
    graph = build_directional_graph(root, histories, reputations)
    graph.update({
        "chain_id": str(chain_id), "depth": 2 if expansion else 1,
        "expanded_nodes": expansion, "failed_expansions": failed_expansions,
        "expansion_limit": expansion_limit, "reputation_limit": 20,
        "coverage": "partial" if failed_expansions or len(reputation_targets) < len(all_addresses - {root.lower()}) else "available",
        "sample_complete": False,
    })
    return graph
