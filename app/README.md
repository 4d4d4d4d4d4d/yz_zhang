# AdForge

A go-global landing + demo site for an AI ad-rendering product. Built with **Vue 3 + Vite**, multi-language (EN / 中文 / 日本語 / Español), and live, interactive demos of every core capability.

## What's inside

- **Home** — animated video hero, stats, features, three-step flow, CTA band
- **Product** — feature grid, **AI Recommendation Engine**, **Campaign Planner**, **Risk & Legal Compliance** (GDPR / CCPA / APPI / C2PA)
- **Studio** — live **Render Studio** simulator (asset → market → format → queue), and a **Deal Copilot** that drafts, translates, and risk-checks cross-border partnership messages
- **Cases** — customer stories with metrics
- **Pricing** — Starter / Growth / Scale with monthly-yearly toggle
- **About** — values, distributed offices
- **Contact** — partnership form, direct channels, and a **Partner Matcher** that scores network partners by category × market × stage

All marketing surfaces, all interactive demos, all dynamic copy are translated across four locales — switchable from the navbar and persisted in `localStorage`.

## Run locally

```bash
cd app
npm install
npm run dev      # http://localhost:5173
npm run test     # unit tests (Vitest) for src/logic
npm run build    # production build → dist/
npm run preview  # serve the build
```

## Architecture: specs, logic layer, tests

Commercialization capabilities are built spec-first — see [`docs/specs/`](../docs/specs/)
for the reviewed design of each domain (architecture, recommendations,
marketing, matchmaking, negotiation, risk & legal, showcase & trust).

Domain algorithms live in `src/logic/` as pure, framework-free modules
(recommendation ranking with explanations, ROAS water-fill budget allocation,
partner fit scoring, ZOPA / playbook term evaluation, market compliance
gates, trust scoring + scoped share links + a bounded-concurrency
verification queue). Each module is covered by unit tests in `tests/`.

The **Console → Video Showcase** section is the trust surface for closing
cross-border deals: provenance-signed video work with evidence-backed badges,
least-privilege expiring trust links (watermark enforced whenever assets are
shared), and a live view of the priority verification queue.

The **Console → Immersive Suite** section covers the in-person half of
going global, online: a digital-human studio (script → timed storyboard →
per-language presenter variants, synthetic-media disclosure always on),
an immersive meeting room with live glossary-protected captions and a
cross-timezone scheduler, a VR-style virtual factory tour (walkway-graph
navigation, coverage tracking, adaptive bitrate that degrades but never
denies), and a field-verification network — vetted local specialists whose
on-site evidence lands in a tamper-evident hash chain before attestation.

## Stack

- Vue 3 (Composition API)
- Vue Router 4
- Vue I18n 9
- Vite 5
- Hand-written design system (CSS variables, no framework dependency)

## Structure

```
app/
├── public/                 # static assets (favicon)
├── src/
│   ├── App.vue
│   ├── main.js
│   ├── styles/global.css   # design tokens + base styles
│   ├── router/             # routes
│   ├── i18n/               # vue-i18n + locales/{en,zh,ja,es}.js
│   ├── components/
│   │   ├── Navbar.vue          # nav + language switcher
│   │   ├── Footer.vue
│   │   ├── LangSwitcher.vue
│   │   ├── VideoHero.vue       # animated canvas + floating ad mocks
│   │   ├── SectionHeader.vue
│   │   ├── FeatureGrid.vue
│   │   ├── StatStrip.vue
│   │   ├── LogoCloud.vue
│   │   ├── AIRecommend.vue     # AI recommendation engine demo
│   │   ├── CampaignPlanner.vue # phased campaign plan
│   │   ├── ComplianceCard.vue  # risk + legal coverage
│   │   ├── RenderStudio.vue    # live render simulator
│   │   ├── NegotiationCopilot.vue # deal copilot chat
│   │   └── PartnerMatcher.vue  # partner suggestion engine
│   └── views/
│       ├── Home.vue
│       ├── Product.vue
│       ├── Studio.vue
│       ├── Cases.vue
│       ├── Pricing.vue
│       ├── About.vue
│       └── Contact.vue
├── index.html
├── package.json
└── vite.config.js
```
