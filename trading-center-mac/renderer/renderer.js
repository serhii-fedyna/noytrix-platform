const root = document.querySelector('#app');
const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;' }[char]));

function activationView(error = '') {
  root.innerHTML = `
    <div class="eyebrow">MAC DESKTOP · SECURE ACTIVATION</div>
    <h1>Control the system.<br/><em>Not your emotions.</em></h1>
    <p class="lead">Connect this Mac to your Noytrix Trading Center license. Your private session is stored only on this device.</p>
    <form class="activation-card" id="activation-form">
      <h2>Activate Noytrix</h2><p>Use the same email and license key issued for your account.</p>
      <label for="email">Email</label><input id="email" type="email" autocomplete="email" required />
      <label for="license">License key</label><input id="license" autocomplete="off" required />
      <button type="submit">Activate this Mac</button><div class="error">${escapeHtml(error)}</div>
    </form>`;
  document.querySelector('#activation-form').addEventListener('submit', activate);
}

async function activate(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = 'Activating…';
  try {
    await window.trading.activate({ email: document.querySelector('#email').value, license_key: document.querySelector('#license').value });
    await dashboardView();
  } catch (error) { activationView(error.message || 'Activation failed.'); }
}

async function dashboardView() {
  root.innerHTML = `<div class="eyebrow">NOYTRIX CONTROL LAYER</div><h1>Trading with a<br/><em>safer system.</em></h1><p class="lead">Reading the authenticated status of your Demo Futures trading engine.</p><section class="status-card"><h2>Loading secure status…</h2><p>This Mac is verifying its protected server session.</p></section>`;
  try {
    const state = await window.trading.status();
    const isRunning = Boolean(state.running);
    root.innerHTML = `
      <div class="eyebrow">NOYTRIX CONTROL LAYER</div><h1>Trading with a<br/><em>safer system.</em></h1>
      <p class="lead">This Mac is connected to your protected Demo Futures control layer.</p>
      <section class="status-card"><h2>Engine status</h2><p>Live status from the server — no trading result is promised or implied.</p>
        <div class="status-grid"><div class="metric"><span>Connection</span><strong class="good">Protected</strong></div><div class="metric"><span>Engine</span><strong class="${isRunning ? 'good' : 'warn'}">${isRunning ? 'Running' : 'Paused'}</strong></div><div class="metric"><span>Mode</span><strong>Demo Futures</strong></div></div>
        <button class="refresh" id="refresh">Refresh status</button>
      </section><p class="legal">Noytrix Trading Center is a software control layer. It does not provide investment advice and does not guarantee profit. Review every setting before enabling a trading engine.</p>`;
    document.querySelector('#refresh').addEventListener('click', dashboardView);
  } catch (error) { activationView(`Session check failed: ${error.message || 'unknown error'}`); }
}

(async () => { const state = await window.trading.currentActivation(); state.active ? dashboardView() : activationView(); })();
