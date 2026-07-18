# Architecture Overview

Confidential technical due diligence draft.

## Product Surfaces

| Surface | Path | Role |
| --- | --- | --- |
| Mobile | `mobile/` | End-user app for scans, PRO, profile, calendar, notifications |
| Backend | `backend/` | FastAPI API, intelligence engine, subscriptions, analytics, admin dashboard |
| Web | `web/` | Public website and web product surface |
| Extension | `extension/` | Browser extension for Web3 runtime protection |
| Telegram bot | `telegram-bot/` | Fast scan interface for Telegram users |
| Lead monitor | `lead-monitor/` | Lead collection and monitoring |
| Trader | `trader/` | Trading service and related APIs |
| Infrastructure | `infrastructure/` | Nginx, systemd, deploy support |

## Backend Capabilities

- URL/domain scanning.
- Wallet and contract scanning.
- Token/ticker enrichment.
- Runtime transaction and signature analysis.
- AI security explanation.
- Internal verdict core.
- Noytrix Scam Database.
- Source reputation.
- Entity reputation and graph risk propagation.
- Scam campaign clustering.
- Multi-chain context.
- Product analytics.
- Subscription entitlements.
- RevenueCat webhook.
- Company dashboard.
- Calendar event harvesting and reminders.
- OneSignal push notifications.

## Current Architecture

```text
Mobile / Web / Extension / Telegram
        |
        v
FastAPI backend
        |
        +-- Scan engine
        +-- Runtime Web3 engine
        +-- AI explanation layer
        +-- Threat intelligence stores
        +-- Subscription entitlement system
        +-- Product analytics
        +-- Calendar and push workers
        |
        v
SQLite / PostgreSQL-ready stores / External APIs / OneSignal / OpenAI
```

## Production Notes

Current production service:

- `noytrix-backend.service`
- Nginx reverse proxy under `infrastructure/nginx/`
- Systemd service files under `infrastructure/systemd/`

## Scale Risks

| Risk | Current State | Recommended Upgrade |
| --- | --- | --- |
| Backend monolith | Much logic in `backend/main.py` | Split into routers, services, workers |
| Database | Multiple SQLite files | PostgreSQL as primary system of record |
| Workers | In-process loops | Dedicated worker process and job queue |
| Deploy | Manual deployment | CI/CD with tests and rollback |
| Observability | Logs and health checks | Metrics, tracing, alerting, crash analytics |
| Secrets | Local env files exist | Managed secrets store |

## Investor-Grade Target

To reach international scale:

- API service separated from background workers.
- PostgreSQL migrations with version control.
- Redis or queue-backed jobs.
- Centralized structured logging.
- Uptime monitoring and incident alerts.
- Automated CI tests and deployment gates.
- Environment separation: dev, staging, production.
