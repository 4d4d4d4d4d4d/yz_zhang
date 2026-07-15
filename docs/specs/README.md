# AdForge Specs Index

Spec-first development: every capability domain is designed and reviewed
here before code. Each spec carries a **Review record** with the decisions
(and rejections) that shaped the design. Logic lives in `app/src/logic/`,
tests in `app/tests/` — the spec's "Test plan" section is the source of
the test assertions.

| # | Spec | Domain module | Tests |
|---|---|---|---|
| 00 | [Architecture: modules, concurrency, security](00-architecture.md) | — | — |
| 01 | [AI Recommendation Engine](01-recommend.md) | `logic/recommend.js` | `tests/recommend.test.js` |
| 02 | [Ad Marketing: budget & pacing](02-marketing.md) | `logic/marketing.js` | `tests/marketing.test.js` |
| 03 | [Business Matchmaking](03-matchmaking.md) | `logic/matching.js` | `tests/matching.test.js` |
| 04 | [Commercial Negotiation](04-negotiation.md) | `logic/negotiation.js` | `tests/negotiation.test.js` |
| 05 | [Risk & Legal Compliance](05-risk-legal.md) | `logic/riskLegal.js` | `tests/riskLegal.test.js` |
| 06 | [Video Showcase & Trust Links](06-showcase-trust.md) | `logic/showcase.js` | `tests/showcase.test.js` |
| 07 | [Digital Human · AI Marketing Video](07-digital-human.md) | `logic/avatar.js` | `tests/avatar.test.js` |
| 08 | [Cross-Language · Immersive Meetings](08-language-immersive-meeting.md) | `logic/interpreter.js`, `logic/meeting.js` | `tests/interpreter.test.js`, `tests/meeting.test.js` |
| 09 | [Virtual Factory Tour](09-virtual-tour.md) | `logic/tour.js` | `tests/tour.test.js` |
| 10 | [Field Verification Network](10-field-verification.md) | `logic/fieldVerify.js` | `tests/fieldVerify.test.js` |
| 11 | [Trust Pipeline: evidence → signature](11-trust-pipeline.md) | `logic/pipeline.js` | `tests/pipeline.test.js` |
| 12 | [CI & Test Maintenance](12-ci-quality.md) | `.github/workflows/ci.yml` | CI itself |
| 13 | [Inline-Algorithm Migration](13-logic-migration.md) | `logic/bandit.js`, `logic/render.js`, `logic/forecast.js` (+ `PartnerMatcher` reuses `logic/matching.js`) | `tests/bandit.test.js`, `tests/render.test.js`, `tests/forecast.test.js` |
| 14 | [Localization Completeness & Message Safety](14-i18n-completeness.md) | `i18n/locales/*` (`console.tabs`) | `tests/i18n.test.js` |
| 15 | [Quote-to-Cash: CPQ · Rev-Rec · Metering](15-quote-to-cash.md) | `logic/cpq.js`, `logic/revrec.js`, `logic/metering.js` | `tests/quoteToCash.test.js` |
| 16 | [Customer Success: Health · Churn · SLA](16-customer-success.md) | `logic/customerSuccess.js` | `tests/customerSuccess.test.js` |
| 17 | [Marketplace Commission (+ queue close-out)](17-commission.md) | `logic/commission.js` | `tests/commission.test.js` |
| 18 | [Logic-Layer Coverage Gate](18-coverage-gate.md) | `vite.config.js`, `.github/workflows/ci.yml` | enforced on the whole `tests/` suite |
| 19 | [Cross-Domain Contract Tests](19-cross-domain-contracts.md) | composes 01/05/06/10/11 | `tests/integration.pipeline.test.js` |
| 20 | [Single-Source Console Registry](20-console-registry.md) | `src/console/registry.js` | `tests/registry.test.js` (+ drives `tests/i18n.test.js`) |
| 21 | [Automated Component Mount-Smoke](21-mount-smoke.md) | all views + section components | `tests/mount.smoke.test.js` |
| 22 | [Architecture Conformance](22-architecture-conformance.md) | rules of specs 00 §2 · 13 R2 | `tests/architecture.test.js` |
| 23 | [GTM Trust Journey (+ SPA nav fix)](23-gtm-trust-journey.md) | `components/TrustJourney.vue`, `App.vue` | `tests/navigation.smoke.test.js` |
| 24 | [⌘K Command Palette](24-command-palette.md) | `logic/search.js`, `components/CommandPalette.vue` | `tests/search.test.js` |
| 25 | [Multi-Currency Pricing](25-multi-currency.md) | `logic/currency.js`, `views/Pricing.vue` | `tests/currency.test.js` |
| 26 | [Notification Center](26-notification-center.md) | `logic/notifications.js`, `components/NotificationCenter.vue` | `tests/notifications.test.js` |
| 27 | [Workspace Data Layer (batch)](27-workspace-data-layer.md) | `data/workspace.js`, `store/workspace.js`, `components/ModuleBoundary.vue` | `tests/workspace.test.js` |
| 28 | [A11y · Bundle Budget · Titles (batch)](28-a11y-budget-titles.md) | overlays a11y, `logic/bundleBudget.js`, `composables/useDocumentTitle.js` | `tests/a11y.test.js`, `tests/bundleBudget.test.js` |

Capability flow across domains:

```
recommend (01) ──► marketing (02) ──► showcase evidence (06,07)
matchmaking (03) ──► meetings & tours (08,09) ──► field verification (10)
        └──────────► negotiation (04) ◄── compliance gates (05)
                              │
                    trust pipeline (11): evidence → verification →
                    compliance → commercial → READY TO SIGN
```
