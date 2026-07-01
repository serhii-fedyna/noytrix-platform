from __future__ import annotations

from typing import Any, Dict, List


RISK_BY_SELECTOR = {
    "095ea7b3": ("approve", "token_approval", 80),
    "a22cb465": ("setApprovalForAll", "nft_collection_approval", 92),
    "d505accf": ("permit", "signature_permission", 88),
    "2b67b570": ("permit2", "signature_permission", 90),
    "30f28b7a": ("permit2", "signature_permission", 90),
    "23b872dd": ("transferFrom", "asset_transfer", 96),
    "a9059cbb": ("transfer", "asset_transfer", 45),
}


def build_execution_graph(tx_decoded: Dict[str, Any] | None) -> Dict[str, Any]:
    tx = tx_decoded or {}

    if not tx:
        return {
            "available": False,
            "root": None,
            "nodes": [],
            "edges": [],
            "risk_paths": [],
            "max_risk": 0,
            "summary": "No decoded transaction available.",
        }

    root_id = "node_0"
    nodes: List[Dict[str, Any]] = [{
        "id": root_id,
        "type": tx.get("type") or "unknown",
        "method": tx.get("method") or "unknown",
        "selector": tx.get("selector"),
        "risk_type": tx.get("risk_type"),
        "severity": 10,
        "metadata": {
            "spender": tx.get("spender"),
            "unlimited": tx.get("unlimited"),
            "can_spend": tx.get("can_spend"),
            "asset_type": tx.get("asset_type"),
        },
    }]
    edges: List[Dict[str, Any]] = []
    risk_paths: List[Dict[str, Any]] = []

    max_risk = 10

    nested = tx.get("nested_selectors") or {}
    found = nested.get("found") or []

    for i, item in enumerate(found, start=1):
        selector = str(item.get("selector") or "").lower()
        method, risk_type, severity = RISK_BY_SELECTOR.get(
            selector,
            (item.get("method") or "unknown", item.get("risk") or "unknown", 30),
        )

        node_id = f"node_{i}"

        node = {
            "id": node_id,
            "type": item.get("type") or method,
            "method": method,
            "selector": selector,
            "risk_type": risk_type,
            "severity": severity,
            "count": int(item.get("count") or 1),
            "positions": item.get("positions") or [],
            "metadata": {
                "hidden": True,
                "inside": tx.get("type") or "unknown",
            },
        }

        nodes.append(node)
        edges.append({
            "from": root_id,
            "to": node_id,
            "relation": "contains_call",
            "confidence": 80,
        })

        max_risk = max(max_risk, severity)

        if severity >= 80:
            risk_paths.append({
                "path": [root_id, node_id],
                "risk_type": risk_type,
                "severity": severity,
                "explanation": f"{method} detected inside {tx.get('method') or tx.get('type')}.",
            })

    direct_type = str(tx.get("type") or "")
    if direct_type in {"erc20_approve", "nft_set_approval_for_all", "permit_or_permit2", "erc20_transfer_from"}:
        direct_risk = {
            "erc20_approve": ("token_approval", 80),
            "nft_set_approval_for_all": ("nft_collection_approval", 92),
            "permit_or_permit2": ("signature_permission", 90),
            "erc20_transfer_from": ("asset_transfer", 96),
        }.get(direct_type, ("unknown", 30))

        nodes[0]["severity"] = direct_risk[1]
        nodes[0]["risk_type"] = direct_risk[0]
        max_risk = max(max_risk, direct_risk[1])
        risk_paths.append({
            "path": [root_id],
            "risk_type": direct_risk[0],
            "severity": direct_risk[1],
            "explanation": f"Direct {tx.get('method') or direct_type} call detected.",
        })

    return {
        "available": True,
        "root": root_id,
        "nodes": nodes,
        "edges": edges,
        "risk_paths": sorted(risk_paths, key=lambda x: int(x.get("severity") or 0), reverse=True),
        "max_risk": max_risk,
        "summary": (
            "Critical execution path detected."
            if max_risk >= 90
            else "High-risk execution path detected."
            if max_risk >= 70
            else "No critical execution path detected."
        ),
    }



def _selector_hits_from_calldata(raw: str) -> List[Dict[str, Any]]:
    h = str(raw or "").lower().replace("0x", "")
    hits: List[Dict[str, Any]] = []

    for selector, info in RISK_BY_SELECTOR.items():
        start = 0
        while True:
            idx = h.find(selector, start)
            if idx == -1:
                break
            method, risk_type, severity = info
            hits.append({
                "selector": selector,
                "position": idx,
                "method": method,
                "risk_type": risk_type,
                "severity": severity,
            })
            start = idx + len(selector)

    return sorted(hits, key=lambda x: int(x.get("position") or 0))


def build_recursive_execution_graph(raw: str, max_depth: int = 4) -> Dict[str, Any]:
    h = str(raw or "").lower().replace("0x", "")

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    risk_paths: List[Dict[str, Any]] = []
    max_risk = 0

    def add_node(
        node_type: str,
        method: str,
        selector: str | None,
        severity: int,
        depth: int,
        position: int | None = None,
        parent: str | None = None,
    ) -> str:
        node_id = f"node_{len(nodes)}"
        nodes.append({
            "id": node_id,
            "type": node_type,
            "method": method,
            "selector": selector,
            "severity": int(severity or 0),
            "depth": depth,
            "position": position,
            "parent": parent,
        })
        return node_id

    root_selector = h[:8] if len(h) >= 8 else None
    root_method, root_risk, root_severity = RISK_BY_SELECTOR.get(root_selector or "", ("root_call", "unknown", 10))
    root_id = add_node("root", root_method, root_selector, root_severity, 0, 0, None)

    visited = set()

    def walk(parent_id: str, segment: str, depth: int, path: List[str]):
        nonlocal max_risk

        if depth >= max_depth:
            return

        key = (parent_id, depth, segment[:256])
        if key in visited:
            return
        visited.add(key)

        hits = _selector_hits_from_calldata(segment)

        for hit in hits:
            selector = str(hit["selector"] or "")

            if depth == 0 and int(hit.get("position") or 0) == 0:
                continue

            method = hit["method"]
            risk_type = hit["risk_type"]
            severity = int(hit["severity"] or 0)
            position = int(hit.get("position") or 0)

            node_id = add_node(
                node_type=method,
                method=method,
                selector=selector,
                severity=severity,
                depth=depth + 1,
                position=position,
                parent=parent_id,
            )

            edges.append({
                "from": parent_id,
                "to": node_id,
                "relation": "contains_nested_call",
                "confidence": min(95, 70 + depth * 5),
            })

            max_risk = max(max_risk, severity)

            current_path = path + [node_id]

            if severity >= 80:
                risk_paths.append({
                    "path": current_path,
                    "risk_type": risk_type,
                    "severity": severity,
                    "depth": depth + 1,
                    "explanation": f"Nested {method} call detected at depth {depth + 1}.",
                })

            tail = segment[position + 8:]

            # If current node is another multicall/batch call, continue from its tail.
            if selector in {"ac9650d8", "5ae401dc"}:
                walk(node_id, tail, depth + 1, current_path)

            # Also continue shallow scanning after dangerous selectors to catch chains in packed calldata.
            elif depth + 1 < max_depth and len(tail) >= 8:
                child_hits = _selector_hits_from_calldata(tail)
                if child_hits:
                    walk(node_id, tail, depth + 1, current_path)

    walk(root_id, h, 0, [root_id])

    deduped_paths = []
    seen_path_keys = set()

    for rp in sorted(risk_paths, key=lambda x: int(x.get("severity") or 0), reverse=True):
        key = (
            tuple(rp.get("path") or []),
            rp.get("risk_type"),
            int(rp.get("severity") or 0),
        )
        if key in seen_path_keys:
            continue
        seen_path_keys.add(key)
        deduped_paths.append(rp)

    attack_steps = []
    seen_attack_step_keys = set()

    for node in nodes:
        if int(node.get("severity") or 0) >= 80:
            key = (node.get("method"), node.get("selector"), int(node.get("severity") or 0))
            if key in seen_attack_step_keys:
                continue
            seen_attack_step_keys.add(key)

            attack_steps.append({
                "node": node.get("id"),
                "method": node.get("method"),
                "selector": node.get("selector"),
                "severity": node.get("severity"),
                "depth": node.get("depth"),
            })

    human_steps = []
    seen_human_steps = set()

    for step in sorted(attack_steps, key=lambda x: int(x.get("severity") or 0), reverse=True):
        method = step.get("method")

        if method == "approve":
            text = "Hidden token approval detected inside the transaction."
        elif method == "setApprovalForAll":
            text = "Hidden NFT collection-wide approval detected."
        elif method == "permit" or method == "permit2":
            text = "Hidden signature permission detected."
        elif method == "transferFrom":
            text = "Hidden transferFrom call detected, which may move assets from a wallet."
        else:
            text = f"Hidden risky call detected: {method}."

        if text not in seen_human_steps:
            seen_human_steps.add(text)
            human_steps.append(text)

    attack_chain_score = max_risk
    if len(deduped_paths) >= 2:
        attack_chain_score = min(100, attack_chain_score + 5)
    if max((int(n.get("depth") or 0) for n in nodes), default=0) >= 2:
        attack_chain_score = min(100, attack_chain_score + 5)

    attack_chain_level = (
        "critical" if attack_chain_score >= 90 else
        "high" if attack_chain_score >= 70 else
        "medium" if attack_chain_score >= 40 else
        "low" if attack_chain_score > 0 else
        "safe"
    )

    return {
        "available": bool(h),
        "recursive": True,
        "attack_chain_score": attack_chain_score,
        "attack_chain_level": attack_chain_level,
        "max_depth": max((int(n.get("depth") or 0) for n in nodes), default=0),
        "nodes": nodes,
        "edges": edges,
        "risk_paths": deduped_paths,
        "attack_chain_summary": {
            "has_attack_chain": bool(deduped_paths),
            "step_count": len(attack_steps),
            "steps": sorted(attack_steps, key=lambda x: int(x.get("severity") or 0), reverse=True),
            "highest_risk_step": sorted(attack_steps, key=lambda x: int(x.get("severity") or 0), reverse=True)[0] if attack_steps else None,
            "human_readable_steps": human_steps,
            "plain_summary": " ".join(human_steps) if human_steps else "No hidden dangerous execution chain detected.",
        },
        "max_risk": max_risk,
        "summary": (
            "Critical nested execution path detected."
            if max_risk >= 90
            else "High-risk nested execution path detected."
            if max_risk >= 70
            else "No critical nested execution path detected."
        ),
    }

