# NOYTRIX Project Map

Last reviewed: 2026-07-01

The workspace is organized as one clean working folder with one directory per product.

## Structure

```text
NOYTRIX-Code/
├─ mobile/
├─ backend/
├─ web/
├─ extension/
├─ telegram-bot/
├─ lead-monitor/
├─ trader/
├─ infrastructure/
│  ├─ nginx/
│  ├─ systemd/
│  └─ deploy/
├─ docs/
├─ AGENTS.md
├─ .gitignore
└─ README.md
```

## Product Map

| Product | Path | Description |
| --- | --- | --- |
| Mobile | `mobile/` | Expo / React Native app with native Android/iOS projects. |
| Backend | `backend/` | FastAPI backend. |
| Web | `web/` | Public static website and landing/API pages. |
| Extension | `extension/` | Browser extension. |
| Telegram bot | `telegram-bot/` | Production Telegram bot. |
| Lead monitor | `lead-monitor/` | Lead collection and notification service. |
| Trader | `trader/` | Trader service/API source. |
| Nginx | `infrastructure/nginx/` | Nginx site configs from production snapshot. |
| Systemd | `infrastructure/systemd/` | Systemd unit files from production snapshot. |
| Deploy | `infrastructure/deploy/` | Deployment support and local preserved secrets state. |

## Protected Local State

`infrastructure/deploy/preserved-local-state/secrets/` contains secret files preserved during cleanup because `.env*`, `google-services.json`, and `*.jks` were explicitly protected from deletion. Treat this folder as local-only.

## Git Notes

Some product folders still contain nested `.git` directories:

- `web/.git`
- `extension/.git`
- `trader/.git`
- public feed repositories under `backend/data/public_feeds/*/.git`

Do not remove these until the repository strategy is decided.
