# Noytrix Brain Delivery Roadmap

## Phase 0: Architecture And Guardrails

- Define isolated module boundaries, data model, audit trail, rate limits,
  source policy, and approval workflow.
- Verify existing OpenAI, SMTP, PostgreSQL intelligence, and Admin Telegram
  integrations without exposing secrets.
- Outcome: a buildable design that does not interrupt Noytrix product services.

## MVP: Pipeline 2 Partnership Intelligence

- Public-source registry and bounded discovery runs.
- Company/domain deduplication and factual dossiers.
- Transparent partnership score and priority queue.
- Evidence-grounded OpenAI outreach draft.
- Admin Telegram notification and daily digest.
- Manual approval endpoint; sender disabled by default.
- Isolated operational data store, unit tests, health endpoint, audit history.

**Done when:** a real public company can be discovered, researched, scored,
shown in a dossier, drafted for, reviewed, and reported without duplicate or
unsupported outreach.

## Version 2: Shared Intelligence Platform

- Migrate Brain operational store to PostgreSQL with Alembic migrations.
- Add Redis, Celery workers, Celery Beat, retries, dead-letter queues, and
  per-source quotas.
- Add reply/delivery webhooks through a provider adapter.
- Build internal dashboard for queue, dossiers, approvals, outcomes, and reports.
- Add pipeline 4 community/influencer discovery and pipeline 5 investor research.
- Add OpenTelemetry traces, structured logs, alerts, backups, and retention policy.

## Version 3: Scale And Learning

- Add jobs pipeline and Altrixos buyer pipeline with isolated policy rules.
- Add Qdrant-backed evidence retrieval and relationship graph views.
- Add controlled learning from aggregate reply and meeting outcomes.
- Add approved-segment automation, warm-intro workflows, and A/B tests after
  deliverability and complaint thresholds are consistently safe.
- Introduce multi-tenant permissions, billing, and customer-facing controls only
  if Noytrix Brain becomes a product.

## Non-Goals For MVP

- No automatic mass outreach.
- No bypassing social network restrictions, login walls, or paywalls.
- No data broker imports or personal-contact harvesting.
- No claims that a target was researched when evidence is absent.
