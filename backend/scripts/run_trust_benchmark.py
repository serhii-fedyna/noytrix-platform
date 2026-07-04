import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import runtime_analyze, security_analyze_core  # noqa: E402


SAFE_OFFICIAL_CRYPTO = [
    "https://bitcoin.org",
    "https://ethereum.org",
    "https://coinbase.com",
    "https://binance.com",
    "https://kraken.com",
    "https://crypto.com",
    "https://ledger.com",
    "https://trezor.io",
    "https://metamask.io",
    "https://trustwallet.com",
    "https://phantom.app",
    "https://rabby.io",
    "https://uniswap.org",
    "https://app.uniswap.org",
    "https://pancakeswap.finance",
    "https://opensea.io",
    "https://blur.io",
    "https://aave.com",
    "https://curve.fi",
    "https://lido.fi",
    "https://jup.ag",
    "https://raydium.io",
    "https://1inch.io",
    "https://compound.finance",
    "https://balancer.fi",
    "https://chain.link",
    "https://solana.com",
    "https://polygon.technology",
    "https://arbitrum.io",
    "https://optimism.io",
    "https://base.org",
    "https://avalanche.network",
    "https://near.org",
    "https://cosmos.network",
    "https://ton.org",
    "https://sui.io",
    "https://aptosfoundation.org",
    "https://etherscan.io",
    "https://bscscan.com",
    "https://polygonscan.com",
    "https://arbiscan.io",
    "https://basescan.org",
    "https://solscan.io",
    "https://tonscan.org",
    "https://coingecko.com",
    "https://coinmarketcap.com",
    "https://defillama.com",
    "https://dune.com",
    "https://zapper.xyz",
    "https://zerion.io",
    "https://safe.global",
    "https://revoke.cash",
    "https://walletconnect.com",
    "https://rainbow.me",
    "https://zerion.io",
    "https://ens.domains",
    "https://snapshot.org",
    "https://tally.xyz",
    "https://debank.com",
]

SAFE_WALLETS = [
    "0x0000000000000000000000000000000000000000",
    "0x00000000219ab540356cBB839Cbe05303d7705Fa",
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    "0x6B175474E89094C44Da98b954EedeAC495271d0F",
]

MALICIOUS_TEXT_CASES = [
    "Connect your wallet to claim a limited USDT airdrop. Verify your seed phrase to unlock rewards.",
    "Support asks for your private key to restore access to MetaMask. Enter recovery phrase now.",
    "Urgent wallet validation required. Sign approval to receive bonus NFT and unlock withdrawal.",
    "Your Binance wallet is suspended. Deposit ETH to activate verification and claim reward.",
    "Airdrop checker requires seed phrase and unlimited token approval before claim.",
    "Wallet migration portal asks users to paste recovery phrase and approve all tokens.",
    "Fake support says to sign a permit transaction to unlock frozen USDC.",
    "Claim reward: connect wallet, approve unlimited USDT, then enter seed phrase for verification.",
]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _flatten_feed_items(data: Any) -> list[str]:
    out: list[str] = []
    stack = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
    for item in stack:
        if isinstance(item, str):
            value = item
        elif isinstance(item, dict):
            value = item.get("url") or item.get("domain") or item.get("address") or item.get("target") or ""
        else:
            continue
        value = str(value).strip()
        if not value or len(value) > 180:
            continue
        if "." in value and not value.startswith(("http://", "https://")):
            value = "https://" + value.strip("/")
        if value.startswith(("http://", "https://", "0x")):
            out.append(value)
    return out


def load_public_feed_samples(limit: int) -> list[str]:
    candidates: list[str] = []
    paths = [
        ROOT / "data/public_feeds/scamsniffer_scam_database/blacklist/domains.json",
        ROOT / "data/public_feeds/scamsniffer_scam_database/blacklist/all.json",
        ROOT / "data/public_feeds/scamsniffer_scam_database/blacklist/combined.json",
        ROOT / "data/public_feeds/cryptoscamdb/blacklist.json",
        ROOT / "data/public_feeds/openphish/feed.json",
    ]
    for path in paths:
        if path.exists():
            candidates.extend(_flatten_feed_items(_read_json(path)))

    random.Random(42).shuffle(candidates)
    deduped: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
        if len(deduped) >= limit:
            break
    return deduped


def approve_data(spender: str) -> str:
    spender_hex = spender.lower().replace("0x", "")
    return "0x095ea7b3" + ("0" * 24) + spender_hex + ("f" * 64)


def build_cases(feed_limit: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for value in SAFE_OFFICIAL_CRYPTO:
        cases.append({"kind": "scan", "id": "safe_domain:" + value, "input": value, "expect": "not_high"})
    for value in SAFE_WALLETS:
        cases.append({"kind": "scan", "id": "safe_wallet:" + value, "input": value, "expect": "not_high"})
    for idx, value in enumerate(MALICIOUS_TEXT_CASES, 1):
        cases.append({"kind": "scan", "id": f"malicious_text:{idx}", "input": value, "expect": "not_safe"})
    for value in load_public_feed_samples(feed_limit):
        cases.append({"kind": "scan", "id": "public_feed:" + value, "input": value, "expect": "not_safe"})

    cases.extend([
        {
            "kind": "runtime",
            "id": "runtime:safe_wallet_connect_uniswap",
            "expect": "runtime_safe",
            "payload": {
                "data": None,
                "method": "eth_requestAccounts",
                "domain": "app.uniswap.org",
                "input": "https://app.uniswap.org/",
                "provider": "ethereum",
                "wallet": "0x00000000219ab540356cBB839Cbe05303d7705Fa",
                "from": "0x00000000219ab540356cBB839Cbe05303d7705Fa",
                "flags": ["wallet_connect"],
                "approve_unlimited": False,
            },
        },
        {
            "kind": "runtime",
            "id": "runtime:trusted_permit2_unlimited_warn_only",
            "expect": "runtime_warn_not_block",
            "payload": {
                "data": approve_data("0x000000000022d473030f116ddee9f6b43ac78ba3"),
                "method": "eth_sendTransaction",
                "domain": "app.uniswap.org",
                "provider": "ethereum",
                "wallet": "0x00000000219ab540356cBB839Cbe05303d7705Fa",
                "from": "0x00000000219ab540356cBB839Cbe05303d7705Fa",
                "flags": ["unlimited_approval", "approval_function"],
                "spender": "0x000000000022d473030f116ddee9f6b43ac78ba3",
                "approve_unlimited": True,
            },
        },
        {
            "kind": "runtime",
            "id": "runtime:unknown_unlimited_approve_block",
            "expect": "runtime_block",
            "payload": {
                "data": approve_data("0x1111111111111111111111111111111111111111"),
                "method": "eth_sendTransaction",
                "domain": "claim-reward.example",
                "provider": "ethereum",
                "wallet": "0x00000000219ab540356cBB839Cbe05303d7705Fa",
                "from": "0x00000000219ab540356cBB839Cbe05303d7705Fa",
                "flags": ["unlimited_approval", "approval_function"],
                "spender": "0x1111111111111111111111111111111111111111",
                "approve_unlimited": True,
            },
        },
    ])
    return cases


def _result_contract(result: dict[str, Any]) -> dict[str, Any]:
    return result.get("runtime_contract") or ((result.get("details") or {}).get("runtime_contract") or {})


def pass_case(case: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str, str]:
    level = str(result.get("level") or "").lower()
    score = int(result.get("score") or 0)
    contract = _result_contract(result)
    investigation = result.get("ai_investigation") or {}
    hypothesis = str(investigation.get("primary_hypothesis") or "").lower()

    if case["expect"] == "not_high":
        hard = bool(((result.get("details") or {}).get("hard_evidence_found")))
        ok = level not in {"danger", "critical", "high", "malicious", "scam"} and score < 60 and not hard
        return ok, f"expected no high-risk false positive, got {level}/{score}", "false_positive"
    if case["expect"] == "not_safe":
        ok = level not in {"safe", "low"} and score >= 30
        return ok, f"expected scam/risk detection, got {level}/{score}", "false_negative"
    if case["expect"] == "runtime_safe":
        ok = level == "safe" and score < 30 and not contract.get("should_warn") and not contract.get("should_block") and "confirmed high-risk" not in hypothesis
        return ok, f"expected safe runtime, got {level}/{score} warn={contract.get('should_warn')} block={contract.get('should_block')} ai={hypothesis}", "runtime_false_positive"
    if case["expect"] == "runtime_warn_not_block":
        ok = bool(contract.get("should_warn")) and not bool(contract.get("should_block")) and score < 70
        return ok, f"expected warning without block, got {level}/{score} warn={contract.get('should_warn')} block={contract.get('should_block')}", "runtime_policy"
    if case["expect"] == "runtime_block":
        ok = bool(contract.get("should_warn")) and bool(contract.get("should_block")) and level in {"high", "critical", "danger"} and score >= 70
        return ok, f"expected block, got {level}/{score} warn={contract.get('should_warn')} block={contract.get('should_block')}", "runtime_false_negative"
    return True, "ok", "unknown"


async def analyze_case(case: dict[str, Any], sem: asyncio.Semaphore, idx: int) -> dict[str, Any]:
    async with sem:
        try:
            if case["kind"] == "runtime":
                result = await asyncio.wait_for(runtime_analyze(case["payload"]), timeout=60)
            else:
                result = await asyncio.wait_for(security_analyze_core({
                    "input": case["input"],
                    "lang": "en",
                    "is_pro": True,
                    "internal_only": True,
                }), timeout=60)
            ok, reason, failure_type = pass_case(case, result)
        except asyncio.TimeoutError:
            result = {"error": "timeout"}
            ok, reason, failure_type = False, "timeout", "timeout"
        except Exception as exc:
            result = {"error": str(exc)}
            ok, reason, failure_type = False, "exception", "exception"

        contract = _result_contract(result)
        investigation = result.get("ai_investigation") or {}
        return {
            "idx": idx,
            "id": case["id"],
            "kind": case["kind"],
            "expect": case["expect"],
            "ok": ok,
            "failure_type": None if ok else failure_type,
            "reason": reason,
            "level": result.get("level"),
            "score": result.get("score"),
            "runtime_warn": contract.get("should_warn"),
            "runtime_block": contract.get("should_block"),
            "ai_primary_hypothesis": investigation.get("primary_hypothesis"),
            "ai_summary": investigation.get("summary"),
            "top": ((result.get("details") or {}).get("top_score_contributors") or [])[:3],
        }


async def run(args: argparse.Namespace) -> int:
    cases = build_cases(args.feed_limit)
    sem = asyncio.Semaphore(args.concurrency)
    tasks = [asyncio.create_task(analyze_case(case, sem, idx)) for idx, case in enumerate(cases, 1)]
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for task in asyncio.as_completed(tasks):
        row = await task
        results.append(row)
        if not row["ok"]:
            failures.append(row)
        if args.verbose or not row["ok"]:
            print(json.dumps(row, ensure_ascii=False), flush=True)

    by_type: dict[str, int] = {}
    for row in failures:
        by_type[row["failure_type"] or "unknown"] = by_type.get(row["failure_type"] or "unknown", 0) + 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "failure_types": by_type,
        "thresholds": {
            "allowed_false_positives": 0,
            "allowed_runtime_policy_failures": 0,
            "allowed_false_negatives": args.allowed_false_negatives,
        },
        "failures": failures,
        "results": sorted(results, key=lambda x: x["idx"]),
    }

    report_dir = ROOT / "tests/reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "trust_benchmark_latest.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    false_positive_failures = sum(v for k, v in by_type.items() if "false_positive" in k)
    runtime_policy_failures = by_type.get("runtime_policy", 0)
    false_negative_failures = sum(v for k, v in by_type.items() if "false_negative" in k)
    passed_gate = (
        false_positive_failures == 0
        and runtime_policy_failures == 0
        and false_negative_failures <= args.allowed_false_negatives
        and by_type.get("exception", 0) == 0
        and by_type.get("timeout", 0) == 0
    )

    print(f"Noytrix Trust Benchmark: {report['passed']}/{report['total']} passed")
    print(f"Failures: {by_type or {}}")
    print(f"Report: {report_path}")
    return 0 if passed_gate else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Noytrix trust benchmark before release.")
    parser.add_argument("--feed-limit", type=int, default=250, help="Maximum scam feed indicators to sample.")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent checks.")
    parser.add_argument("--allowed-false-negatives", type=int, default=0, help="Temporary tolerance for missed scam feed samples.")
    parser.add_argument("--verbose", action="store_true", help="Print every result, not only failures.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
