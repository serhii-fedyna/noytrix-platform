import asyncio
import json
import random
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import security_analyze_core  # noqa: E402


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
    "https://uniswap.org",
    "https://app.uniswap.org",
    "https://pancakeswap.finance",
    "https://opensea.io",
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
]

SAFE_WALLETS = [
    "0x0000000000000000000000000000000000000000",
    "0x00000000219ab540356cBB839Cbe05303d7705Fa",
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
]

MALICIOUS_TEXT_CASES = [
    "Connect your wallet to claim a limited USDT airdrop. Verify your seed phrase to unlock rewards.",
    "Support asks for your private key to restore access to MetaMask. Enter recovery phrase now.",
    "Urgent wallet validation required. Sign approval to receive bonus NFT and unlock withdrawal.",
    "Your Binance wallet is suspended. Deposit ETH to activate verification and claim reward.",
    "Airdrop checker requires seed phrase and unlimited token approval before claim.",
]


def load_scamsniffer_samples(limit: int = 40) -> list[str]:
    candidates: list[str] = []
    paths = [
        ROOT / "data/public_feeds/scamsniffer_scam_database/blacklist/domains.json",
        ROOT / "data/public_feeds/scamsniffer_scam_database/blacklist/all.json",
        ROOT / "data/public_feeds/scamsniffer_scam_database/blacklist/combined.json",
    ]
    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        stack = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
        for item in stack:
            if isinstance(item, str):
                value = item
            elif isinstance(item, dict):
                value = item.get("url") or item.get("domain") or item.get("address") or item.get("target") or ""
            else:
                continue
            value = str(value).strip()
            if not value or len(value) > 160:
                continue
            if "." in value and not value.startswith(("http://", "https://")):
                value = "https://" + value.strip("/")
            if value.startswith(("http://", "https://", "0x")):
                candidates.append(value)
    random.Random(42).shuffle(candidates)
    deduped = []
    seen = set()
    for value in candidates:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
        if len(deduped) >= limit:
            break
    return deduped


def build_cases() -> list[dict]:
    cases = []
    for value in SAFE_OFFICIAL_CRYPTO:
        cases.append({"id": "safe:" + value, "input": value, "expect": "not_high"})
    for value in SAFE_WALLETS:
        cases.append({"id": "safe_wallet:" + value, "input": value, "expect": "not_high"})
    for value in MALICIOUS_TEXT_CASES:
        cases.append({"id": "malicious_text:" + str(len(cases)), "input": value, "expect": "not_safe"})
    for value in load_scamsniffer_samples(100):
        cases.append({"id": "public_feed:" + value, "input": value, "expect": "not_safe"})
        if len(cases) >= 100:
            break
    return cases[:100]


def pass_case(case: dict, result: dict) -> tuple[bool, str]:
    level = str(result.get("level") or "").lower()
    score = int(result.get("score") or 0)
    if case["expect"] == "not_high":
        ok = level not in {"danger", "critical", "high", "malicious", "scam"} and score < 60
        return ok, f"expected not high, got {level}/{score}"
    if case["expect"] == "not_safe":
        ok = level not in {"safe", "low"} and score >= 30
        return ok, f"expected not safe, got {level}/{score}"
    return True, "ok"


async def run_one(idx: int, case: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        try:
            result = await asyncio.wait_for(
                security_analyze_core({
                    "input": case["input"],
                    "lang": "en",
                    "is_pro": True,
                    "internal_only": True,
                }),
                timeout=25,
            )
            ok, reason = pass_case(case, result)
        except asyncio.TimeoutError:
            result = {"error": "timeout"}
            ok, reason = False, "timeout"
        except Exception as exc:
            result = {"error": str(exc)}
            ok, reason = False, "exception"
        return {
            "idx": idx,
            "id": case["id"],
            "input": case["input"],
            "expect": case["expect"],
            "ok": ok,
            "reason": reason,
            "level": result.get("level"),
            "score": result.get("score"),
            "hard_evidence": ((result.get("details") or {}).get("hard_evidence_found")),
            "safety_gate": ((result.get("details") or {}).get("false_positive_safety_gate") or {}).get("applied"),
            "top": ((result.get("details") or {}).get("top_score_contributors") or [])[:3],
        }


async def main() -> int:
    cases = build_cases()
    sem = asyncio.Semaphore(8)
    tasks = [asyncio.create_task(run_one(idx, case, sem)) for idx, case in enumerate(cases, 1)]
    results = []
    failures = []
    for task in asyncio.as_completed(tasks):
        row = await task
        results.append(row)
        if not row["ok"]:
            failures.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    report_dir = ROOT / "tests/reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "accuracy_100_latest.json"
    report_path.write_text(json.dumps({
        "total": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "failures": failures,
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Accuracy 100: {len(cases) - len(failures)}/{len(cases)} passed")
    print(f"Report: {report_path}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
