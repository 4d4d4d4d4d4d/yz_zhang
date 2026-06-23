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
npm run build    # production build → dist/
npm run preview  # serve the build
```

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
