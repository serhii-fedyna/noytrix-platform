# Noytrix Chat-First Staging Redesign

## Scope

This is an isolated visual and interaction prototype in `web/staging/`. It does not replace the production site or change backend, authentication, entitlement, billing, or analytics behavior.

## Existing pieces reused

- Noytrix brand asset: `web/favicon.png`.
- Existing live scan route: `GET /scan?input=...&lang=en`.
- Existing Noytrix account destination: `api-dashboard.html`.
- Existing palette: deep navy, white typography, signature orange, and green/yellow/red risk states.

## Staging component tree

```text
AppShell
  Sidebar
    NewCheck
    SecuritySessionHistory
    AccountLink
  Workspace
    EmptySecurityState
      InteractiveShield
      UniversalScanComposer
      QuickExamples
    LiveAnalysisStatus
    VerdictMessage
    FollowUpComposer (display-only in this visual stage)
    MonitoringConfirmation
```

## State model

- `closed`: shield is shown; it opens the composer.
- `open`: user can paste one security object or write a question.
- `scanning`: the existing backend endpoint is requested. The UI only claims that the request is live; it does not fabricate security findings.
- `result`: backend response is rendered in the same session.
- `failed`: a contained error state leaves the input usable.

## API and product work deliberately not changed

The following need backend/product work before this preview can become a new production primary flow:

- streamed analysis-stage events;
- persistent web security-session history;
- AI follow-up endpoint with scan context;
- web monitoring creation and delivery;
- server-side FREE follow-up allowance based on the existing entitlement source of truth.

## Validation expectations

- A real scan must continue to use the existing `/scan` endpoint.
- The preview must remain `noindex`.
- The staging host must not share the production web root or modify production Nginx routes.
