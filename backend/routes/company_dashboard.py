import hmac
import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from product_analytics import company_dashboard


load_dotenv("/root/backend/.env")

router = APIRouter()

COMPANY_DASHBOARD_PASSWORD = (os.getenv("COMPANY_DASHBOARD_PASSWORD") or "Minoas2020").strip()


def _valid_company_dashboard_password(request: Request) -> bool:
    got = (
        request.headers.get("x-dashboard-password")
        or request.headers.get("X-Dashboard-Password")
        or ""
    ).strip()
    auth = (request.headers.get("authorization") or request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        got = auth[7:].strip()
    return bool(COMPANY_DASHBOARD_PASSWORD and got and hmac.compare_digest(got, COMPANY_DASHBOARD_PASSWORD))


@router.get("/admin/company-dashboard/data")
async def company_dashboard_data(request: Request, days: int = 30):
    if not _valid_company_dashboard_password(request):
        raise HTTPException(status_code=401, detail="invalid_dashboard_password")
    return company_dashboard(days=days)


COMPANY_DASHBOARD_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Noytrix - РµР¶РµРґРЅРµРІРЅР°СЏ СЃС‚Р°С‚РёСЃС‚РёРєР°</title>
  <style>
    :root {
      --bg: #06080f;
      --panel: rgba(11, 18, 39, 0.84);
      --panel2: rgba(17, 27, 56, 0.78);
      --line: rgba(255, 255, 255, 0.10);
      --gold: #ffb020;
      --gold2: #ff8a00;
      --text: #f5f7ff;
      --muted: #a8b4cf;
      --bad: #ff6565;
      --blue: #66b3ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 20% 5%, rgba(255,176,32,0.20), transparent 26rem),
        radial-gradient(circle at 80% 0%, rgba(30,80,220,0.22), transparent 32rem),
        linear-gradient(135deg, #06080f 0%, #081021 48%, #0b1c4f 100%);
      min-height: 100vh;
    }
    body:before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255,255,255,0.032) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.032) 1px, transparent 1px);
      background-size: 18px 18px;
      mask-image: linear-gradient(to bottom, #000 0%, transparent 95%);
    }
    .wrap { position: relative; max-width: 1520px; margin: 0 auto; padding: 26px; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 18px 0 24px; }
    .brand { display: flex; align-items: center; gap: 14px; }
    .logo {
      width: 42px; height: 42px; border-radius: 10px; display: grid; place-items: center;
      background: #07102b; color: var(--gold); border: 1px solid rgba(255,176,32,0.24);
      box-shadow: 0 18px 60px rgba(255,176,32,0.14); font-weight: 900;
    }
    h1 { margin: 0; font-size: 28px; letter-spacing: 0; }
    .sub { color: var(--muted); margin-top: 4px; font-size: 14px; }
    .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
    select, input, button {
      border: 1px solid var(--line); background: rgba(255,255,255,0.06); color: var(--text);
      border-radius: 12px; padding: 12px 14px; font-weight: 750; outline: none;
    }
    option { background: #10172d; color: var(--text); }
    button {
      cursor: pointer; background: linear-gradient(135deg, var(--gold), var(--gold2)); color: #09101f;
      border: 0; box-shadow: 0 18px 50px rgba(255,176,32,0.23);
    }
    .login {
      max-width: 520px; margin: 12vh auto; padding: 28px; border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(20,28,54,0.96), rgba(8,13,28,0.96));
      border-radius: 18px; box-shadow: 0 30px 90px rgba(0,0,0,0.42);
    }
    .login input { width: 100%; margin: 18px 0 12px; background: #e8eefb; color: #050814; font-size: 16px; }
    .login button { width: 100%; font-size: 16px; }
    .hidden { display: none !important; }
    .status { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; color: var(--muted); font-size: 13px; }
    .pill {
      display: inline-flex; align-items: center; gap: 8px; border: 1px solid rgba(255,176,32,0.25);
      background: rgba(255,176,32,0.09); color: #ffd37a; border-radius: 999px; padding: 8px 12px; font-weight: 800;
    }
    .section {
      margin-top: 20px; padding: 18px; border: 1px solid var(--line); border-radius: 18px;
      background: rgba(7, 12, 28, 0.58); backdrop-filter: blur(18px);
    }
    .section h2 { margin: 0 0 14px; font-size: 18px; }
    .cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
    .card { min-height: 108px; padding: 16px; border: 1px solid var(--line); border-radius: 14px; background: linear-gradient(180deg, var(--panel), var(--panel2)); }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; font-weight: 850; }
    .value { margin-top: 10px; font-size: 28px; font-weight: 950; letter-spacing: 0; }
    .note { margin-top: 8px; color: var(--muted); font-size: 12px; line-height: 1.35; }
    .empty { color: rgba(168,180,207,0.72); font-size: 18px; }
    table { width: 100%; border-collapse: collapse; overflow: hidden; }
    th, td { text-align: left; padding: 11px 10px; border-bottom: 1px solid rgba(255,255,255,0.08); font-size: 13px; }
    th { color: var(--muted); text-transform: uppercase; font-size: 11px; }
    .tables { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
    .tablebox { border: 1px solid var(--line); border-radius: 14px; overflow: auto; background: rgba(6,8,15,0.45); }
    .barrow { display: grid; grid-template-columns: 110px 1fr 60px; gap: 10px; align-items: center; margin: 8px 0; color: var(--muted); }
    .bar { height: 8px; background: rgba(255,255,255,0.08); border-radius: 999px; overflow: hidden; }
    .bar span { display: block; height: 100%; background: linear-gradient(90deg, var(--gold), var(--blue)); border-radius: inherit; }
    .error { color: var(--bad); margin-top: 10px; font-weight: 750; }
    @media (max-width: 1100px) { .cards { grid-template-columns: repeat(2, 1fr); } .tables { grid-template-columns: 1fr; } }
    @media (max-width: 720px) { .wrap { padding: 16px; } header { align-items: flex-start; flex-direction: column; } .cards { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main class="wrap">
    <section id="login" class="login">
      <div class="brand">
        <div class="logo">N</div>
        <div>
          <h1>РЎС‚Р°С‚РёСЃС‚РёРєР° Noytrix</h1>
          <div class="sub">Р—Р°РєСЂС‹С‚Р°СЏ СЃС‚СЂР°РЅРёС†Р° СЃ СЂРµР°Р»СЊРЅС‹РјРё РґР°РЅРЅС‹РјРё РїРѕ РїСЂРёР»РѕР¶РµРЅРёСЋ, РїРѕР»СЊР·РѕРІР°С‚РµР»СЏРј Рё РѕРїР»Р°С‚Р°Рј.</div>
        </div>
      </div>
      <input id="password" type="password" placeholder="РџР°СЂРѕР»СЊ" autocomplete="current-password" />
      <button onclick="login()">РћС‚РєСЂС‹С‚СЊ СЃС‚Р°С‚РёСЃС‚РёРєСѓ</button>
      <div id="loginError" class="error"></div>
    </section>

    <section id="dashboard" class="hidden">
      <header>
        <div class="brand">
          <div class="logo">N</div>
          <div>
            <h1>РЎС‚Р°С‚РёСЃС‚РёРєР° Noytrix</h1>
            <div class="sub">РџРѕР»СЊР·РѕРІР°С‚РµР»Рё, Р°РЅР°Р»РёР·С‹, РІРѕР·РІСЂР°С‚С‹, РѕРїР»Р°С‚С‹ Рё РєР°С‡РµСЃС‚РІРѕ. РўРѕР»СЊРєРѕ СЂРµР°Р»СЊРЅС‹Рµ РґР°РЅРЅС‹Рµ СЃ СЃРµСЂРІРµСЂР°.</div>
          </div>
        </div>
        <div class="controls">
          <span class="pill" id="freshness">Р—Р°РіСЂСѓР·РєР°</span>
          <select id="days" onchange="loadData()">
            <option value="1">РЎРµРіРѕРґРЅСЏ</option>
            <option value="7">7 РґРЅРµР№</option>
            <option value="30" selected>30 РґРЅРµР№</option>
            <option value="90">90 РґРЅРµР№</option>
            <option value="0">Р—Р° РІСЃС‘ РІСЂРµРјСЏ</option>
          </select>
          <button onclick="loadData()">РћР±РЅРѕРІРёС‚СЊ</button>
          <button onclick="logout()">Р’С‹Р№С‚Рё</button>
        </div>
      </header>
      <div class="status" id="status"></div>
      <div id="sections"></div>
    </section>
  </main>

  <script>
    const keyName = "noytrixCompanyDashboardPassword";
    let refreshTimer = null;

    function fmtMetric(metric) {
      if (!metric || metric.value === null || metric.value === undefined || metric.value === "") return '<span class="empty">РџРѕРєР° РЅРµС‚ РґР°РЅРЅС‹С…</span>';
      const unit = metric.unit ? ` ${metric.unit}` : "";
      if (typeof metric.value === "number") return `${metric.value.toLocaleString("en-US")}${unit}`;
      return `${metric.value}${unit}`;
    }
    function card(label, metric) {
      const note = metric && metric.note ? `<div class="note">${metric.note}</div>` : "";
      return `<div class="card"><div class="label">${label}</div><div class="value">${fmtMetric(metric)}</div>${note}</div>`;
    }
    function section(title, cards) {
      return `<section class="section"><h2>${title}</h2><div class="cards">${cards.join("")}</div></section>`;
    }
    function table(title, rows, cols) {
      const head = cols.map(c => `<th>${c.label}</th>`).join("");
      const body = (rows || []).slice(0, 20).map(row => `<tr>${cols.map(c => `<td>${row[c.key] ?? ""}</td>`).join("")}</tr>`).join("");
      return `<div class="tablebox"><table><thead><tr><th colspan="${cols.length}">${title}</th></tr><tr>${head}</tr></thead><tbody>${body || `<tr><td colspan="${cols.length}">РџРѕРєР° РЅРµС‚ РґР°РЅРЅС‹С…</td></tr>`}</tbody></table></div>`;
    }
    function dailyBars(rows) {
      const max = Math.max(1, ...(rows || []).map(x => x.scans || 0));
      return `<section class="section"><h2>РџСЂРѕРІРµСЂРєРё РїРѕ РґРЅСЏРј</h2>${(rows || []).map(x => {
        const pct = Math.round(((x.scans || 0) / max) * 100);
        return `<div class="barrow"><span>${x.day}</span><div class="bar"><span style="width:${pct}%"></span></div><strong>${x.scans || 0}</strong></div>`;
      }).join("") || '<div class="note">РџРѕРєР° РЅРµС‚ РµР¶РµРґРЅРµРІРЅС‹С… РґР°РЅРЅС‹С….</div>'}</section>`;
    }
    async function fetchDashboard() {
      const password = sessionStorage.getItem(keyName) || "";
      const days = document.getElementById("days").value || "30";
      const response = await fetch(`/admin/company-dashboard/data?days=${encodeURIComponent(days)}`, {
        headers: { "X-Dashboard-Password": password }
      });
      if (!response.ok) throw new Error(response.status === 401 ? "РќРµРІРµСЂРЅС‹Р№ РїР°СЂРѕР»СЊ." : `РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃС‚Р°С‚РёСЃС‚РёРєСѓ: ${response.status}`);
      return response.json();
    }
    async function loadData() {
      try { render(await fetchDashboard()); }
      catch (error) {
        document.getElementById("status").innerHTML = `<span class="error">${String(error.message || error)}</span>`;
        if (String(error.message || "").includes("РќРµРІРµСЂ")) logout(false);
        throw error;
      }
    }
    function render(data) {
      document.getElementById("freshness").textContent = data.dataFreshness?.lastEventAt ? `РџРѕСЃР»РµРґРЅРµРµ СЃРѕР±С‹С‚РёРµ: ${data.dataFreshness.lastEventAt}` : "РЎРѕР±С‹С‚РёР№ РїРѕРєР° РЅРµС‚";
      document.getElementById("status").innerHTML = `
        <span>РћР±РЅРѕРІР»РµРЅРѕ: ${data.generatedAt}</span>
        <span>РџРµСЂРёРѕРґ: ${data.windowDays === 0 ? "Р·Р° РІСЃС‘ РІСЂРµРјСЏ" : `${data.windowDays} РґРЅРµР№`}</span>
        <span>РќРѕРІС‹Рµ СЃРѕР±С‹С‚РёСЏ РІ Р±Р°Р·Рµ: ${data.dataFreshness?.eventRows || 0}</span>
        <span>РЎС‚Р°СЂС‹Рµ СЃРѕР±С‹С‚РёСЏ Р°РЅР°Р»РёР·РѕРІ: ${data.dataFreshness?.historicProfileEvents || 0}</span>
        <span>Р‘Р°Р·Р° РїРѕРґРїРёСЃРѕРє: ${data.dataFreshness?.subscriptionsDb ? "РїРѕРґРєР»СЋС‡РµРЅР°" : "РЅРµ РЅР°Р№РґРµРЅР°"}</span>
        <span>Р•СЃР»Рё РЅР°РїРёСЃР°РЅРѕ вЂњРџРѕРєР° РЅРµС‚ РґР°РЅРЅС‹С…вЂќ, Р·РЅР°С‡РёС‚ СЃРµСЂРІРµСЂ РµС‰С‘ РЅРµ РїРѕР»СѓС‡РёР» С‚Р°РєРѕРµ СЃРѕР±С‹С‚РёРµ РѕС‚ РїСЂРёР»РѕР¶РµРЅРёСЏ РёР»Рё СЂРµРєР»Р°РјС‹.</span>
      `;
      const a = data.acquisition || {}, ac = data.activation || {}, r = data.retention || {}, rev = data.revenue || {}, q = data.quality || {};
      document.getElementById("sections").innerHTML = [
        section("РџСЂРёРІР»РµС‡РµРЅРёРµ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№", [
          card("РЈСЃС‚Р°РЅРѕРІРєРё РїСЂРёР»РѕР¶РµРЅРёСЏ", a.installs),
          card("Р¦РµРЅР° РѕРґРЅРѕР№ СѓСЃС‚Р°РЅРѕРІРєРё", a.costPerInstall),
          card("Р РµРіРёСЃС‚СЂР°С†РёРё", a.registrations),
          card("Р¦РµРЅР° РѕРґРЅРѕР№ СЂРµРіРёСЃС‚СЂР°С†РёРё", a.costPerRegistration),
        ]),
        section("РџРµСЂРІС‹Рµ РґРµР№СЃС‚РІРёСЏ РІ РїСЂРёР»РѕР¶РµРЅРёРё", [
          card("РЎРґРµР»Р°Р»Рё РїРµСЂРІС‹Р№ Р°РЅР°Р»РёР·", ac.firstAnalysisUsers),
          card("РЈСЃС‚Р°РЅРѕРІРёР»Рё Рё РґРѕС€Р»Рё РґРѕ Р°РЅР°Р»РёР·Р°", ac.installToAnalysisConversion),
          card("Р’СЂРµРјСЏ РґРѕ РїРµСЂРІРѕРіРѕ Р°РЅР°Р»РёР·Р°", ac.averageMinutesToFirstAnalysis),
          card("РЈСЃРїРµС€РЅС‹Рµ Р°РЅР°Р»РёР·С‹ Р±РµР· РѕС€РёР±РєРё", ac.usefulResultsWithoutError),
          card("Р”РѕР»СЏ СѓСЃРїРµС€РЅС‹С… Р°РЅР°Р»РёР·РѕРІ", ac.usefulResultRate),
        ]),
        section("Р’РѕР·РІСЂР°С‚С‹ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№", [
          card("Р’РµСЂРЅСѓР»РёСЃСЊ РЅР° СЃР»РµРґСѓСЋС‰РёР№ РґРµРЅСЊ", r.returnedNextDay),
          card("Р’РµСЂРЅСѓР»РёСЃСЊ С‡РµСЂРµР· 7 РґРЅРµР№", r.returnedDay7),
          card("РђРЅР°Р»РёР·РѕРІ РЅР° Р°РєС‚РёРІРЅРѕРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ", r.analysesPerActiveUser),
          card("РђРєС‚РёРІРЅС‹Рµ СЃРµРіРѕРґРЅСЏ", r.dailyActiveUsers),
          card("РђРєС‚РёРІРЅС‹Рµ Р·Р° РјРµСЃСЏС†", r.monthlyActiveUsers),
        ]),
        section("Р”РµРЅСЊРіРё Рё РїРѕРґРїРёСЃРєРё", [
          card("РћС‚РєСЂС‹Р»Рё СЌРєСЂР°РЅ РѕРїР»Р°С‚С‹", rev.paywallViewedUsers),
          card("РќР°Р¶Р°Р»Рё РєСѓРїРёС‚СЊ", rev.purchaseStartedUsers),
          card("РџРѕРєСѓРїРєР° Р·Р°РІРµСЂС€РµРЅР°", rev.purchaseCompletedUsers),
          card("Р РµР°Р»СЊРЅС‹Рµ РїР»Р°С‚РЅС‹Рµ PRO СЃРµР№С‡Р°СЃ", rev.activePaidSubscriptions),
          card("Р’СЃРµРіРѕ Р°РєС‚РёРІРЅС‹С… PRO-РґРѕСЃС‚СѓРїРѕРІ", rev.totalActiveProAccess),
          card("РџРµСЂРµРЅРµСЃС‘РЅРЅС‹Р№ СЃС‚Р°СЂС‹Р№ PRO", rev.legacyActiveProAccess),
          card("Р СѓС‡РЅРѕР№ PRO-РґРѕСЃС‚СѓРї", rev.manualActiveProAccess),
          card("РўРµСЃС‚РѕРІС‹Рµ PRO-Р°РєРєР°СѓРЅС‚С‹", rev.testActiveProAccess),
          card("РџСЂРёРјРµСЂРЅР°СЏ РјРµСЃСЏС‡РЅР°СЏ РІС‹СЂСѓС‡РєР°", rev.monthlyRecurringRevenue),
          card("РћС‚РјРµРЅС‹ РїРѕРґРїРёСЃРѕРє", rev.cancellations),
          card("Р’РѕР·РІСЂР°С‚С‹ РґРµРЅРµРі", rev.refunds),
          card("РђРєС‚РёРІРЅС‹Рµ Р·Р°РїРёСЃРё РїРѕРґРїРёСЃРѕРє РІ Р±Р°Р·Рµ", rev.activeSubscriptionRows),
        ]),
        section("РљР°С‡РµСЃС‚РІРѕ СЂР°Р±РѕС‚С‹", [
          card("РџСЂРѕС†РµРЅС‚ РѕС€РёР±РѕРє Р°РЅР°Р»РёР·Р°", q.analysisErrorRate),
          card("РЎСЂРµРґРЅРµРµ РІСЂРµРјСЏ РѕС‚РІРµС‚Р° СЃРµСЂРІРµСЂР°", q.averageResponseTimeMs),
          card("РџР°РґРµРЅРёСЏ РїСЂРёР»РѕР¶РµРЅРёСЏ", q.appCrashes),
          card("РћС€РёР±РєРё РѕРїР»Р°С‚С‹", q.paymentErrors),
          card("Р”РѕСЃС‚СѓРїРЅРѕСЃС‚СЊ РїСЂРѕРІРµСЂРѕРє", q.apiAvailability),
        ]),
        `<section class="section"><h2>РСЃС‚РѕС‡РЅРёРєРё Рё СЃС‚СЂР°РЅС‹</h2><div class="tables">
          ${table("РСЃС‚РѕС‡РЅРёРєРё", a.sources || [], [
            {key:"source", label:"РСЃС‚РѕС‡РЅРёРє"}, {key:"campaign", label:"РљР°РјРїР°РЅРёСЏ"}, {key:"installs", label:"РЈСЃС‚Р°РЅРѕРІРєРё"},
            {key:"registrations", label:"Р РµРіРёСЃС‚СЂР°С†РёРё"}, {key:"scans", label:"РђРЅР°Р»РёР·С‹"}, {key:"paywalls", label:"Р­РєСЂР°РЅ РѕРїР»Р°С‚С‹"},
            {key:"purchases", label:"РџРѕРєСѓРїРєРё"}, {key:"cpi", label:"Р¦РµРЅР° СѓСЃС‚Р°РЅРѕРІРєРё"}, {key:"cpr", label:"Р¦РµРЅР° СЂРµРіРёСЃС‚СЂР°С†РёРё"}
          ])}
          ${table("РЎС‚СЂР°РЅС‹", a.countries || [], [
            {key:"country", label:"РЎС‚СЂР°РЅР°"}, {key:"users", label:"РџРѕР»СЊР·РѕРІР°С‚РµР»Рё"}, {key:"events", label:"РЎРѕР±С‹С‚РёСЏ"},
            {key:"installs", label:"РЈСЃС‚Р°РЅРѕРІРєРё"}, {key:"scans", label:"РђРЅР°Р»РёР·С‹"}
          ])}
        </div></section>`,
        dailyBars(data.daily || []),
      ].join("");
    }
    async function login() {
      const password = document.getElementById("password").value.trim();
      sessionStorage.setItem(keyName, password);
      document.getElementById("loginError").textContent = "";
      try {
        await loadData();
        document.getElementById("login").classList.add("hidden");
        document.getElementById("dashboard").classList.remove("hidden");
        if (refreshTimer) clearInterval(refreshTimer);
        refreshTimer = setInterval(loadData, 30000);
      } catch (error) {
        document.getElementById("loginError").textContent = String(error.message || error);
      }
    }
    function logout(clear = true) {
      if (clear) sessionStorage.removeItem(keyName);
      document.getElementById("dashboard").classList.add("hidden");
      document.getElementById("login").classList.remove("hidden");
      if (refreshTimer) clearInterval(refreshTimer);
    }
    document.getElementById("password").addEventListener("keydown", (event) => {
      if (event.key === "Enter") login();
    });
    if (sessionStorage.getItem(keyName)) {
      document.getElementById("password").value = sessionStorage.getItem(keyName);
      login();
    }
  </script>
</body>
</html>
"""


@router.get("/admin/company-dashboard", response_class=HTMLResponse)
async def company_dashboard_page():
    return HTMLResponse(COMPANY_DASHBOARD_HTML)
