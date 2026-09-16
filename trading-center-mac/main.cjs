const { app, BrowserWindow, ipcMain, safeStorage } = require('electron');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const BILLING_URL = 'https://www.noytrix.com/billing/license/activate';
const TRADER_API = 'https://api.noytrixapp.com/trader-api';

function statePath() {
  return path.join(app.getPath('userData'), 'activation.json');
}

function readActivation() {
  try {
    const stored = JSON.parse(fs.readFileSync(statePath(), 'utf8'));
    if (!stored.payload || !safeStorage.isEncryptionAvailable()) return null;
    return JSON.parse(safeStorage.decryptString(Buffer.from(stored.payload, 'base64')));
  } catch {
    return null;
  }
}

function saveActivation(activation) {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('Secure storage is unavailable on this Mac.');
  }
  const encrypted = safeStorage.encryptString(JSON.stringify(activation));
  fs.writeFileSync(statePath(), JSON.stringify({ payload: encrypted.toString('base64') }), { mode: 0o600 });
}

function deviceId() {
  const current = readActivation();
  return current?.device_id || crypto.randomUUID();
}

async function jsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  let body = {};
  try { body = await response.json(); } catch { /* handled below */ }
  if (!response.ok) throw new Error(body.reason || body.detail || `Request failed (${response.status})`);
  return body;
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 680,
    backgroundColor: '#071022',
    title: 'Noytrix Trading Center',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  window.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

ipcMain.handle('activation:current', () => {
  const activation = readActivation();
  return activation ? { active: true, activation } : { active: false, device_id: deviceId() };
});

ipcMain.handle('activation:activate', async (_event, input) => {
  const activation = await jsonRequest(BILLING_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Origin: 'http://tauri.localhost' },
    body: JSON.stringify({
      email: String(input.email || '').trim().toLowerCase(),
      license_key: String(input.license_key || '').trim(),
      device_id: deviceId(),
      device_name: 'Noytrix Trading Center for Mac'
    })
  });
  if (!activation.valid || !activation.session_token) throw new Error('Activation was not completed.');
  saveActivation(activation);
  return activation;
});

ipcMain.handle('trader:status', async () => {
  const activation = readActivation();
  if (!activation?.session_token || !activation?.device_id) throw new Error('Activate this Mac first.');
  return jsonRequest(`${TRADER_API}/bot/status`, {
    headers: {
      'X-Noytrix-Session': activation.session_token,
      'X-Noytrix-Device-Id': activation.device_id
    }
  });
});

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
