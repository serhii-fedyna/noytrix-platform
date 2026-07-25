// app/lib/ai.js
// Lightweight AI helper. Uses the same backend base URL as the rest of the app.
import { BACKEND } from "./backend";

const API_BASE = BACKEND;

const SYSTEM_LIMIT = "Answer only about cryptocurrency, blockchain, DeFi and trading risk topics. For unrelated topics, politely refuse.";

export async function askAI({ prompt, mode = "explain", context = {} }) {
  try {
    const r = await fetch(`${API_BASE}/ai/assist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, prompt, user_id: "anon-" + Date.now(), context, system: SYSTEM_LIMIT }),
    });
    if (r.ok) {
      const j = await r.json();
      if (j?.text) return j.text;
    }
  } catch {}

  return fallbackAnswer(prompt, mode);
}

export async function askAIQuickTip() {
  try {
    const r = await fetch(`${API_BASE}/ai/quick`, { method: "GET" });
    if (r.ok) {
      const j = await r.json();
      if (j?.tip) return j.tip;
    }
  } catch {}
  const tips = [
    "Check the token contract, liquidity and holder concentration before buying.",
    "If a site asks for a seed phrase, close it. A real service never needs it.",
    "Review approval permissions before signing. Unlimited approve can put funds at risk.",
    "High yield promises and urgent countdowns are common scam pressure tactics."
  ];
  return tips[Math.floor(Math.random() * tips.length)];
}

function fallbackAnswer(prompt, mode) {
  const p = String(prompt || "").toLowerCase();
  if (!/btc|eth|sol|usdt|coin|crypto|bitcoin|ether|token|web3|defi|nft/.test(p)) {
    return "AI explanation is unavailable right now. Try again later.";
  }
  const templates = {
    explain:
      "AI explanation is unavailable right now. Try again later.",
    shield:
      "AI explanation is unavailable right now. Try again later.",
    portfolio:
      "AI explanation is unavailable right now. Try again later.",
    alert:
      "AI explanation is unavailable right now. Try again later.",
  };
  return templates[mode] || templates.explain;
}

















