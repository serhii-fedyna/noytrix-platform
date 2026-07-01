# AGENTS

This repository is the working folder for the Noytrix product suite. Keep changes scoped to the product you are working on.

## Product Roots

- `mobile/` - Expo / React Native app.
- `backend/` - FastAPI backend.
- `web/` - public static website.
- `extension/` - browser extension.
- `telegram-bot/` - Telegram bot.
- `lead-monitor/` - lead monitor service.
- `trader/` - trader service.
- `infrastructure/` - nginx, systemd, and deploy support files.

## Rules

- Do not push or deploy without explicit user confirmation.
- Do not delete or rewrite `.env*`, `google-services.json`, or `*.jks` files without a separate secrets-management task.
- Leave nested `.git` directories inside product folders as they are unless the user asks for a Git strategy cleanup.
- Keep generated files, dependency folders, logs, PID files, archives, and backup snapshots out of commits.
