# Noytrix Financial Model

Confidential draft. Replace assumptions with verified data before investor use.

## Model Structure

The model should track three revenue lines:

1. Consumer subscription.
2. API subscription.
3. Enterprise intelligence and partnership revenue.

## Core Inputs

| Input | Current Value | Source | Confidence |
| --- | ---: | --- | --- |
| Monthly app installs | `[insert]` | Google Play Console | To verify |
| Registered users | `[insert]` | Backend users table | To verify |
| Monthly active users | `[insert]` | Product analytics | To verify |
| Monthly scans | `[insert]` | Backend scan events | To verify |
| Free to PRO conversion | `[insert]` | Revenue events | To verify |
| Monthly churn | `[insert]` | Subscription events | To verify |
| Average revenue per paying user | `[insert]` | Google Play / RevenueCat | To verify |
| API paying accounts | `[insert]` | Billing records | To verify |
| Enterprise pipeline value | `[insert]` | B2B pipeline | To verify |

## Revenue Logic

### Consumer Subscription

Formula:

```text
Monthly consumer revenue =
monthly active users
* conversion to paid
* average monthly subscription price
* payment success rate
```

Key controls:

- Purchases must be confirmed server-side.
- Entitlements must be derived from subscriptions, not manual user plan flags.
- Refunds, cancellations, and expirations must update revenue and access.

### API Revenue

Formula:

```text
Monthly API revenue =
starter_accounts * starter_price
+ growth_accounts * growth_price
+ scale_accounts * scale_price
+ enterprise_accounts * enterprise_price
```

### Enterprise Revenue

Enterprise revenue should be modeled separately because sales cycles, onboarding, support, SLA, and custom integrations differ from consumer and API plans.

## Cost Categories

| Category | Description | Monthly Estimate |
| --- | --- | ---: |
| Cloud servers | Backend, databases, monitoring, backups | `[insert]` |
| Third-party APIs | Threat intelligence, chain APIs, AI models | `[insert]` |
| AI usage | OpenAI and related model calls | `[insert]` |
| App stores and payment fees | Google Play, payment processors | `[insert]` |
| Legal and compliance | Counsel, privacy, terms, corporate | `[insert]` |
| Marketing | Ads, content, creators, partnerships | `[insert]` |
| Contractors | Design, engineering, QA, security | `[insert]` |
| Tools | Analytics, logging, uptime, email | `[insert]` |

## Scenario Plan

| Scenario | Description | 12-Month Goal |
| --- | --- | --- |
| Conservative | Organic growth, limited paid acquisition, founder-led execution | Product stability and first paying cohort |
| Base | Mobile acquisition plus API packaging and partner outreach | Predictable subscriptions and early B2B pilots |
| Upside | Strong app growth, extension launch, B2B conversion | Meaningful recurring revenue and enterprise pipeline |

## Investor-Ready Outputs

Before sharing, export:

- Monthly P&L.
- Revenue by line.
- Active paid subscriptions.
- Churn.
- CAC by channel.
- Payback period.
- Gross margin.
- Burn rate.
- Runway.
- 12, 24, and 36-month forecast.
