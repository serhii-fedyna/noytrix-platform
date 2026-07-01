// app/lib/ai.js
// 1Q@B:0 4;O 2K7>20 B2>53> 1M:5=40 A  + 157>?0A=K5 D>;1M:8.
// A;8 C B51O 5ABL A5@25@, A45;09 POST =0 https://api.noytrixapp.com/ai/assist (?@8<5@).
// A;8 A5@25@0 =5B  2AQ @02=> 25@=QB @07C<=K9 >B25B (;>:0;L=>), GB>1K =8G53> =5 ?040;>.

const API_BASE = "https://api.noytrixapp.com"; // ?@8 =5>1E>48<>AB8 70<5=8

const SYSTEM_LIMIT = "/ >B25G0N B>;L:> ?> B5<0< :@8?B>20;NBK, 1;>:G59=0, DeFi, B@5948=30. 0 =5A2O70==K5 B5<K 256;82> >B:07K20NAL.";

export async function askAI({ prompt, mode = "explain", context = {} }) {
  // A=0G0;0 ?@>1C5< @50;L=K9 1M:5=4, 5A;8 >= =0AB@>5=
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

  // D>;1M:: ;>:0;L=0O 8<8B0F8O (GB>1K 2A5340 1K;> GB> ?>:070BL)
  return fallbackAnswer(prompt, mode);
}

// >@>B:89 :@8?B>-D0:B/?>4A:07:0 4;O ?C7K@O C 1>B0
export async function askAIQuickTip() {
  try {
    const r = await fetch(`${API_BASE}/ai/quick`, { method: "GET" });
    if (r.ok) {
      const j = await r.json();
      if (j?.tip) return j.tip;
    }
  } catch {}
  // ;>:0;L=K9 D>;1M:
  const tips = [
    "$0:B: 2KA>:0O :><8AA8O ` 2KA>:89 A?@>A  C A5B8 <>65B 1KBL ?5@53@C7.",
    "45O: 4>102L AB>?-70?@>A 2 ?;0=  A=8605B 8<?C;LA82=K5 >H81:8.",
    "$0:B: @>AB >1JQ<0 @0=LH5 F5=K G0AB> ?@54H5AB2C5B 8<?C;LAC.",
    "0?><8=0=85: ?@>25@O9 :>=B@0:B B>:5=0 8 ;8:284=>ABL ?C;0."
  ];
  return tips[Math.floor(Math.random() * tips.length)];
}

// ?@>ABK5 H01;>==K5 >B25BK, 5A;8 A5@25@ =54>ABC?5=
function fallbackAnswer(prompt, mode) {
  const p = String(prompt || "").toLowerCase();
  if (!/btc|eth|sol|usdt|coin|:@8?B|18B:>|MD8@|B>:5=|web3|defi|nft/.test(p)) {
    return "728=8, O 3>2>@N B>;L:> > :@8?B>20;NB5 8 1;>:G59=5. 0409 :@8?B>-2>?@>A =B";
  }
  const templates = {
    explain:
      ">@>B:>: =>2>ABL/2>?@>A :0A05BAO @K=:0.  8A:8: 2>;0B8;L=>ABL, ;8:284=>ABL, D@>4. 59AB28O: ?@>25@L >1JQ<K, B@5=4 24G/74 8 ;8:284=>ABL. B>3: =59B@0;L=>/C<5@5==> 1KGL5.",
    shield:
      "@>25@:0 =0 A:0<: 4><5= A25689? >15I0=8O 4>E>40? :>=B@0:B A ?@020<8 mint/pause/blacklist? ;8:284=>ABL =5 701;>:8@>20=0? A;8 2+ ?C=:B0  @8A: 2KA>:89.",
    portfolio:
      "57 4>ABC?0 : 10;0=AC: 107>20O AE5<0 100% :0?8B0;0  50% BTC/ETH, 30% mid-cap, 20% :MH/AB591;K. 5=O9 ?>4 A2>9 @8A:-?@>D8;L.",
    alert:
      ";5@B: A;548 70 @57:8< @>AB>< >1JQ<0 >50% ?@8 AB018;L=>< A?@M45  A83=0; : 2=8<0=8N, =5 : ?>:C?:5.",
  };
  return templates[mode] || templates.explain;
}

















