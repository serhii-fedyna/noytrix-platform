# Product Metrics

Confidential draft. Replace placeholders with verified backend, Google Play, RevenueCat, and analytics data.

## North Star Metric

**Completed useful risk checks per active user.**

Why it matters:

- It reflects real user value.
- It is closer to safety behavior than installs.
- It connects product usage to subscription intent.

## Core Funnel

| Stage | Metric | Definition | Source |
| --- | --- | --- | --- |
| Acquisition | Installs | New app installs by day and source | Google Play |
| Activation | First completed scan | User completes first successful analysis | Product analytics |
| Engagement | Repeat scans | User performs more than one scan | Backend events |
| Trust | Risk explanation viewed | User reads AI explanation | Product analytics |
| Monetization | Paywall viewed | User opens PRO screen | Product analytics |
| Monetization | Purchase completed | Server confirms subscription entitlement | Subscriptions system |
| Retention | Day 1 / Day 7 return | User returns after first session | Product analytics |

## Current Metrics Snapshot

| Metric | Current Value | Date | Confidence |
| --- | ---: | --- | --- |
| Installs | `[insert]` | `[date]` | To verify |
| Registered users | `[insert]` | `[date]` | To verify |
| Active users today | `[insert]` | `[date]` | To verify |
| Monthly active users | `[insert]` | `[date]` | To verify |
| Completed scans | `[insert]` | `[date]` | To verify |
| Failed scans | `[insert]` | `[date]` | To verify |
| Active paid subscribers | `[insert]` | `[date]` | To verify |
| Refunds | `[insert]` | `[date]` | To verify |
| Trial starts | `[insert]` | `[date]` | To verify |
| Paywall conversion | `[insert]` | `[date]` | To verify |

## Event Taxonomy

Standard events:

- `app_first_open`
- `session_started`
- `signup_started`
- `signup_completed`
- `scan_started`
- `scan_completed`
- `scan_failed`
- `scan_result_viewed`
- `risk_explanation_viewed`
- `paywall_viewed`
- `trial_started`
- `purchase_started`
- `purchase_completed`
- `purchase_failed`
- `purchase_cancelled`
- `subscription_renewed`
- `subscription_cancelled`
- `subscription_expired`
- `app_feedback_submitted`

## Reporting Standard

Investor metric reports should separate:

- Production users.
- Internal users.
- Test users.
- Refunded users.
- Sandbox purchases.
- Manual promotional access.

Test and internal activity must not be counted as traction.
