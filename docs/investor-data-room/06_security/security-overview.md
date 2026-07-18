# Security Overview

Confidential security due diligence draft.

## Security Objective

Noytrix handles security-sensitive workflows. The company must protect:

- User accounts.
- Subscription and entitlement records.
- Scan history.
- API keys.
- Admin dashboards.
- Threat intelligence data.
- Production credentials.
- Mobile signing credentials.

## Current Security Controls

| Area | Current Control |
| --- | --- |
| Backend service | FastAPI production service behind systemd and reverse proxy |
| API access | App key and auth-protected areas exist |
| Payments | Server-side subscription and entitlement system |
| Revenue events | RevenueCat webhook processing with idempotency concept |
| AI | Backend controls explanation generation |
| Push | OneSignal backend sender with deduplication and pacing |
| Data safety | `.gitignore` protects secrets and generated artifacts |
| Admin dashboard | Password-protected internal dashboard |

## Data Handling Principles

- Do not store private keys, seed phrases, or wallet secrets.
- Do not ask users to enter seed phrases.
- Do not expose raw provider responses when they contain sensitive metadata.
- Do not include secrets in logs.
- Do not commit `.env`, service account JSON, keystores, or database dumps.
- Separate test users from real customers in analytics and revenue reporting.

## Key Risks

| Risk | Severity | Recommendation |
| --- | --- | --- |
| Secrets present in local workspace | High | Move to managed secrets and remove local backups from shareable materials |
| Multiple SQLite databases | Medium | Consolidate production records into PostgreSQL |
| Manual deploy flow | Medium | Add CI/CD, staging, rollback |
| Large backend monolith | Medium | Modularize and add service boundaries |
| Admin dashboard password | Medium | Add stronger auth, audit log, and IP controls |
| AI output reliability | Medium | Enforce fallback behavior and no hardcoded verdicts |
| Push notification overreach | Medium | Keep pacing, preference controls, and opt-out |

## Incident Response Draft

Severity levels:

- SEV-1: user data exposure, payment access issue, production outage.
- SEV-2: scan engine wrong critical behavior, entitlement failure, API outage.
- SEV-3: UI bug, translation issue, delayed notification.

Response process:

1. Identify incident.
2. Stop active harm.
3. Preserve logs.
4. Notify responsible owner.
5. Patch and deploy.
6. Verify production.
7. Write postmortem.
8. Update controls to prevent recurrence.

## Security Roadmap

- Move secrets to managed secret storage.
- Add dependency scanning.
- Add SAST and secret scanning in CI.
- Add database backups and restore testing.
- Add production audit logs.
- Add role-based admin access.
- Add privacy and data retention policy.
- Add formal vulnerability disclosure channel.
