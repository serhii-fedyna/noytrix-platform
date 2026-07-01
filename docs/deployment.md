# Deployment

Last reviewed: 2026-07-01

This document records deployment-related files in the cleaned workspace. It is not a deploy command log.

## Infrastructure Files

| Area | Path |
| --- | --- |
| Nginx configs | `infrastructure/nginx/` |
| Systemd services | `infrastructure/systemd/` |
| Deploy support | `infrastructure/deploy/` |

## Product Entry Points

| Product | Path | Expected entry point |
| --- | --- | --- |
| Mobile | `mobile/` | `package.json`, `app.json`, `eas.json` |
| Backend | `backend/` | `main.py`, `requirements.txt` |
| Web | `web/` | `index.html` |
| Extension | `extension/` | `manifest.json`, `background.js`, `content.js`, `inject.js` |
| Telegram bot | `telegram-bot/` | `bot.py`, `config.py` |
| Lead monitor | `lead-monitor/` | `main.py`, `requirements.txt` |
| Trader | `trader/` | `main.py`, `bot_api.py` |

## Safety Rules

- Do not deploy without explicit confirmation.
- Do not commit `.env*`, `*.db`, `*.log`, `*.pid`, signing keys, archives, or generated dependency folders.
- Treat `infrastructure/deploy/preserved-local-state/secrets/` as local-only preserved secrets, not deploy material.

## Suggested Checks

```powershell
cd mobile
npm install
npx expo config --json
```

```powershell
cd backend
python -m compileall .
```

For static and script-based products, verify expected entry files exist before deploy.
