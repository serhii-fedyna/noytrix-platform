from __future__ import annotations

import os
from typing import Any, Dict, List

from .js_behavior import analyze_js_behavior


HEADLESS_SANDBOX_VERSION = "1.0"


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


def _add_signal(signals: List[Dict[str, Any]], code: str, severity: int, text: str, **extra: Any) -> None:
    item = {
        "code": code,
        "severity": max(0, min(100, int(severity))),
        "text": text,
    }
    item.update(extra)
    signals.append(item)


def _score_wallet_calls(wallet_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    methods = {str(call.get("method") or "").lower() for call in wallet_calls}

    if any(m in methods for m in {"eth_requestaccounts", "wallet_requestpermissions"}):
        _add_signal(signals, "runtime_wallet_connect_request", 25, "Runtime page requested wallet connection.")
    if any("signtypeddata" in m for m in methods):
        _add_signal(signals, "runtime_typed_signature_request", 75, "Runtime page requested an EIP-712 typed signature.")
    if "personal_sign" in methods or "eth_sign" in methods:
        _add_signal(signals, "runtime_message_signature_request", 65, "Runtime page requested a wallet message signature.")
    if "eth_sendtransaction" in methods:
        _add_signal(signals, "runtime_transaction_request", 78, "Runtime page requested a blockchain transaction.")

    joined = str(wallet_calls).lower()
    if any(x in joined for x in ["approve", "permit", "permit2", "setapprovalforall", "transferfrom"]):
        _add_signal(signals, "runtime_approval_or_drain_flow", 92, "Runtime wallet call references approval, permit, or transferFrom behavior.")
    if any(x in joined for x in ["seed phrase", "private key", "recovery phrase"]):
        _add_signal(signals, "runtime_secret_phrase_request", 100, "Runtime page attempted to request wallet secrets.")
    if any("signtypeddata" in m for m in methods) and "eth_requestaccounts" in methods:
        _add_signal(signals, "runtime_connect_plus_signature_flow", 86, "Runtime page combines wallet connect with signature request.")
    if "eth_sendtransaction" in methods and "eth_requestaccounts" in methods:
        _add_signal(signals, "runtime_connect_plus_transaction_flow", 88, "Runtime page combines wallet connect with transaction request.")

    return signals


async def analyze_headless_sandbox(url: str, timeout_ms: int | None = None) -> Dict[str, Any]:
    enabled = str(os.getenv("NOYTRIX_HEADLESS_SANDBOX", "1")).strip().lower() not in {"0", "false", "no", "off"}
    if not enabled:
        return {
            "available": False,
            "version": HEADLESS_SANDBOX_VERSION,
            "reason": "disabled_by_env",
            "score": 0,
            "level": "safe",
            "signals": [],
        }

    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        return {
            "available": False,
            "version": HEADLESS_SANDBOX_VERSION,
            "reason": "playwright_unavailable",
            "error": str(e)[:200],
            "score": 0,
            "level": "safe",
            "signals": [],
        }

    timeout_ms = max(3000, min(int(timeout_ms or os.getenv("NOYTRIX_HEADLESS_TIMEOUT_MS", "9000")), 20000))
    wallet_calls: List[Dict[str, Any]] = []
    console_messages: List[str] = []
    page_errors: List[str] = []
    script_urls: List[str] = []
    html = ""
    final_url = url

    init_script = """
(() => {
  const calls = [];
  const emit = (method, params) => {
    const item = { method, params, href: location.href, ts: Date.now() };
    calls.push(item);
    window.__NOYTRIX_WALLET_CALLS__ = calls.slice(-80);
    window.dispatchEvent(new CustomEvent("__noytrix_wallet_call", { detail: item }));
  };
  const request = async (args) => {
    const method = args && args.method ? String(args.method) : "unknown";
    const params = args && args.params ? args.params : [];
    emit(method, params);
    if (method === "eth_requestAccounts" || method === "eth_accounts") return ["0x000000000000000000000000000000000000dEaD"];
    if (method === "eth_chainId") return "0x1";
    if (method === "net_version") return "1";
    return null;
  };
  const provider = { isMetaMask: true, selectedAddress: "0x000000000000000000000000000000000000dEaD", request, enable: async () => request({ method: "eth_requestAccounts" }), on: () => {}, removeListener: () => {} };
  Object.defineProperty(window, "ethereum", { configurable: true, get: () => provider });
  window.web3 = window.web3 || { currentProvider: provider };
})();
"""

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
            ])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 NoytrixSandbox/1.0",
                ignore_https_errors=True,
                viewport={"width": 1366, "height": 900},
            )
            page = await context.new_page()
            await page.add_init_script(init_script)

            page.on("console", lambda msg: console_messages.append(str(msg.text)[:240]))
            page.on("pageerror", lambda exc: page_errors.append(str(exc)[:240]))
            page.on("request", lambda req: script_urls.append(req.url) if req.resource_type == "script" else None)

            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 6000))
            except Exception:
                pass
            try:
                await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(750)
            except Exception:
                pass

            final_url = page.url
            wallet_calls = await page.evaluate("() => window.__NOYTRIX_WALLET_CALLS__ || []")
            html = await page.content()
            await context.close()
            await browser.close()
    except Exception as e:
        return {
            "available": False,
            "version": HEADLESS_SANDBOX_VERSION,
            "reason": "sandbox_runtime_error",
            "error": str(e)[:300],
            "score": 0,
            "level": "safe",
            "signals": [],
        }

    static_js = analyze_js_behavior(html)
    signals: List[Dict[str, Any]] = []
    signals.extend(_score_wallet_calls(wallet_calls))
    for sig in static_js.get("signals") or []:
        _add_signal(
            signals,
            f"headless_{sig.get('code')}",
            int(sig.get("severity") or 0),
            sig.get("text") or "Runtime HTML JavaScript behavior detected.",
            matches=sig.get("matches") or [],
        )

    if len(script_urls) >= 12:
        _add_signal(signals, "runtime_many_script_loads", 30, "Runtime page loaded many JavaScript resources.")
    if page_errors and wallet_calls:
        _add_signal(signals, "runtime_wallet_flow_with_errors", 45, "Runtime wallet flow produced page errors.")

    score = max([int(s.get("severity") or 0) for s in signals] or [0])
    level = _level(score)

    return {
        "available": True,
        "version": HEADLESS_SANDBOX_VERSION,
        "url": url,
        "final_url": final_url,
        "score": score,
        "level": level,
        "signals": sorted(signals, key=lambda x: int(x.get("severity") or 0), reverse=True)[:30],
        "wallet_calls": wallet_calls[:30],
        "console_messages": console_messages[:20],
        "page_errors": page_errors[:20],
        "script_urls": sorted(dict.fromkeys(script_urls))[:50],
        "summary": (
            "Runtime browser sandbox detected wallet-drainer behavior."
            if score >= 90 else
            "Runtime browser sandbox detected risky wallet behavior."
            if score >= 70 else
            "Runtime browser sandbox completed without critical wallet behavior."
        ),
    }
