import httpx
from typing import Any, Dict, Optional


def _detect_chain_id_for_honeypot(
    etherscan_result: Optional[Dict[str, Any]],
    bscscan_result: Optional[Dict[str, Any]],
) -> Optional[int]:
    if bscscan_result and bscscan_result.get("status") == "ok":
        return 56
    if etherscan_result and etherscan_result.get("status") == "ok":
        return 1
    return None


async def honeypot_check(address: str, chain_id: Optional[int] = None) -> Dict[str, Any]:
    try:
        params = {"address": address}
        if chain_id:
            params["chainID"] = str(chain_id)

        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            r = await client.get("https://api.honeypot.is/v2/IsHoneypot", params=params)
            r.raise_for_status()
            j = r.json()

        summary = j.get("summary") or {}
        hp = j.get("honeypotResult") or {}
        sim = j.get("simulationResult") or {}
        code = j.get("contractCode") or {}
        pair = j.get("pair") or {}
        pair_obj = pair.get("pair") or {}

        risk = str(summary.get("risk") or "").lower()
        risk_level = summary.get("riskLevel")
        is_honeypot = bool(hp.get("isHoneypot", False))
        simulation_success = bool(j.get("simulationSuccess", False))

        buy_tax = sim.get("buyTax")
        sell_tax = sim.get("sellTax")
        transfer_tax = sim.get("transferTax")
        open_source = bool(code.get("openSource", False))
        is_proxy = bool(code.get("isProxy", False))
        liquidity = pair.get("liquidity")

        if is_honeypot:
            status = "warn"
            comment = "Honeypot.is: honeypot detected."
        elif simulation_success:
            status = "ok" if risk in ("very_low", "low", "") else "warn"
            comment = f"Honeypot.is: risk={risk or 'unknown'}."
        else:
            status = "warn"
            comment = "Honeypot.is: simulation failed or pair unavailable."

        return {
            "status": status,
            "comment": comment,
            "risk": risk or None,
            "risk_level": risk_level,
            "is_honeypot": is_honeypot,
            "simulation_success": simulation_success,
            "buy_tax": buy_tax,
            "sell_tax": sell_tax,
            "transfer_tax": transfer_tax,
            "open_source": open_source,
            "is_proxy": is_proxy,
            "liquidity": liquidity,
            "pair_name": pair_obj.get("name"),
            "pair_address": j.get("pairAddress") or pair_obj.get("address"),
            "router": j.get("router"),
            "raw": j,
        }

    except Exception as e:
        return {"status": "error", "comment": f"Honeypot.is error: {e}"}
