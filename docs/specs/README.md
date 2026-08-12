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
| 29 | [Conversion Surface Hardening (batch)](29-conversion-surface.md) | `logic/validation.js`, `logic/analytics.js`, `views/Contact.vue` | `tests/conversion.test.js` |
| 30 | [Funnel Analytics (closes the recorder loop)](30-funnel-analytics.md) | `logic/funnel.js`, `components/FunnelView.vue` | `tests/funnel.test.js` |
| 31 | [Keyboard Nav & A11y (batch)](31-keyboard-nav-a11y.md) | `logic/shortcuts.js`, `components/{SubTabs,GotoShortcuts}.vue`, `App.vue` skip-link | `tests/shortcuts.test.js`, `tests/subtabs.test.js` |
| 32 | [Operator Velocity (batch)](32-operator-velocity.md) | `logic/recents.js`, `shortcutRows()`, `components/ShortcutHelp.vue`, recents in `CommandPalette.vue` | `tests/recents.test.js`, `tests/shortcutHelp.test.js`, `tests/shortcuts.test.js` |
| 33 | [Locale-Aware Figures (staged)](33-locale-figures.md) | `logic/format.js`, `composables/useFormat.js`; adopted in `RevenueDashboard.vue`, `UsageMetering.vue` | `tests/format.test.js` |
| 34 | [Exportable Deal Readiness Report](34-deal-report.md) | `logic/dealReport.js`, `components/DealReportCard.vue`, `showcase/report` sub-tab | `tests/dealReport.test.js` |
| 35 | [Sortable & Exportable Tables](35-sortable-export-tables.md) | `logic/sortRows.js`, `logic/csv.js`, `composables/useSortable.js`; adopted in `OrderBook.vue` | `tests/sortRows.test.js`, `tests/csv.test.js` |
| 36 | [Cross-Timezone Meeting Planner](36-timezone-planner.md) | `logic/timezones.js`, `components/MeetingPlanner.vue`, `immersive/planner` sub-tab | `tests/timezones.test.js` |
| 37 | [Calendar Export & Adjustable Hours](37-ics-calendar.md) | `logic/ics.js`, `MeetingPlanner.vue` (shift presets + .ics download) | `tests/ics.test.js` |
| 38 | [Reduced Motion (OS + user toggle)](38-reduced-motion.md) | `logic/motion.js`, `composables/useReducedMotion.js`, `MotionToggle.vue`, `VideoHero.vue`, global CSS | `tests/motion.test.js` |
| 39 | [Command Palette Actions](39-palette-actions.md) | `logic/commands.js`, `CommandPalette.vue` (runs locale/motion actions) | `tests/commands.test.js` |
| 40 | [Trust-Link Enforced on Read](40-trustlink-enforcement.md) | `logic/showcase.js` `resolveTrustLinkView`, `TrustLinkBuilder.vue` recipient preview | `tests/showcase.test.js` |
| 41 | [Consent-Gated Analytics (GDPR)](41-consent-analytics.md) | `logic/consent.js`, `useAnalytics` gate, `ConsentBanner.vue`, footer reopen | `tests/consent.test.js` |
| 42 | [Data Subject Requests (deadlines)](42-dsr-workflow.md) | `logic/dsr.js`, `ControlsRegister.vue` DSR queue | `tests/dsr.test.js` |
| 43 | [Availability SLA Service Credits](43-sla-credits.md) | `logic/slaCredit.js`, `SupportSLA.vue` availability panel | `tests/slaCredit.test.js` |
| 44 | [Cross-Border Quote (partner currency)](44-cross-border-quote.md) | `logic/quote.js`, `CPQEditor.vue` currency picker | `tests/quote.test.js` |
| 45 | [A/B Statistical Significance](45-ab-significance.md) | `logic/significance.js`, `ExperimentManager.vue` calculator | `tests/significance.test.js` |
| 46 | [Multi-Touch Attribution (computed)](46-attribution-models.md) | `logic/attribution.js`, `AttributionWaterfall.vue` (bars + paths + delta) | `tests/attribution.test.js` |
| 47 | [Sales Forecast (double-count fix + coverage)](47-sales-forecast.md) | `logic/salesForecast.js`, `SalesForecast.vue` | `tests/salesForecast.test.js` |
| 48 | [Forecast Prediction Intervals](48-forecast-uncertainty.md) | `logic/forecast.js` (uncertainty), `ForecastSim.vue` band panel | `tests/forecastUncertainty.test.js` |
| 49 | [ZOPA Band Fix + Surplus Split](49-zopa-surplus.md) | `logic/negotiation.js` (discountZopa/surplusSplit/discountAnchor), `NegotiationPlaybook.vue` | `tests/zopa.test.js` |
| 50 | [Explainable Recommender Wired Up](50-explainable-recommend.md) | `logic/recommend.js` (conceptSignals), `RecommendDeep.vue` | `tests/conceptSignals.test.js` |

Capability flow across domains:

```
recommend (01) ──► marketing (02) ──► showcase evidence (06,07)
matchmaking (03) ──► meetings & tours (08,09) ──► field verification (10)
        └──────────► negotiation (04) ◄── compliance gates (05)
                              │
                    trust pipeline (11): evidence → verification →
                    compliance → commercial → READY TO SIGN
```
