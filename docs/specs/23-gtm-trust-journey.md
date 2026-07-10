# Spec 23 — GTM Surface Alignment: the Trust Journey on the Product Page

Status: **Approved** · Review: R1 (2026-07-05)
Artifacts: `components/TrustJourney.vue`, `views/Product.vue`, `i18n/locales/*` (`product.journey`)

## Problem

The marketing site is the acquisition surface, but the Product page still
tells the v1 story — AI recommendations, campaign planning, compliance.
The capabilities that answer the actual go-global brief (数字视频展示 ·
增加互信 · 促成商业合作) — provenance-signed video showcases, immersive
cross-language meetings, VR factory tours, on-the-ground verification and
the deal-readiness pipeline — exist only inside the console. A prospect
never sees the differentiators before signing up. The product outgrew its
own storefront.

## Design

### `TrustJourney.vue` — the 4-step trust loop, rendered from i18n
A Product-page section narrating how a deal closes across borders:

| Step | Story | Console deep link |
|---|---|---|
| 1 Show | provenance-signed video showcase, verified metrics, trust links | `/console/showcase` |
| 2 Meet | digital humans, live glossary-protected interpreting, VR factory tour | `/console/immersive` |
| 3 Verify | local specialists, tamper-evident evidence chain | `/console/immersive` (field) |
| 4 Sign | compliance gates + playbook terms → deal-readiness score | `/console/showcase` (pipeline) |

- Pure presentation: copy comes from `product.journey.*` i18n keys, links
  from the router — **no logic module needed** (and none added; spec 22's
  conformance scope stays honest).
- Every string in all four locales. This is not aspiration: the spec-14
  key-parity test fails the build if any locale misses a key.

### `Product.vue`
New section between the existing demos and the compliance card, using the
established `SectionHeader` + section rhythm.

## Guard rails exercised (no new test infra needed)
- i18n key parity + compile safety (spec 14) — forces en/zh/ja/es.
- Mount smoke (spec 21) — Product.vue with the new section must mount
  clean in CI.
- Browser smoke — section renders, deep links navigate to the console.

## Test plan
- Suite passes with the new keys (parity proves 4-locale completeness).
- Product mounts clean under the existing mount smoke.
- Browser: journey section visible in en + zh; clicking a step lands on
  the right console section.

## Review record — R1
- ✅ Copy lives in i18n, not the component — the parity guard is the whole
  point; hardcoded strings would bypass it.
- ✅ Deep links go to the live console demos rather than static claims —
  "show, don't tell" is the product's own trust thesis.
- Verdict: **approved**.

## R1 discovery — site-wide SPA navigation was broken (fixed here)

Smoking the journey deep link exposed a **pre-existing, site-wide
defect**: `App.vue` wrapped `router-view` in
`<transition mode="out-in">` whose direct child was the routed
component — but the views are **multi-root** (Product renders four
sibling `<section>`s). Vue 3 transitions require a single element root;
on any in-app navigation the swap fails and the page renders **blank**.
Full page loads (and every previous smoke, which used direct `goto`)
never exercised an in-app route change, so eighteen rounds of testing
missed it. Every navbar click in production would have blanked the site.

Fix: give the transition a single-element child — a wrapper `<div>`
keyed by route **name** (not path, so `/console/:tab` switches don't
remount the console shell):

```html
<transition name="fade" mode="out-in">
  <div :key="String($route.name)"><component :is="Component" /></div>
</transition>
```

Guard: `tests/navigation.smoke.test.js` mounts the real `App` with the
real router, performs in-app navigations (home → product → pricing →
console/showcase) and asserts each destination renders non-trivial
content with no Vue warnings. Verified to fail against the broken
App.vue before the fix landed (teeth), pass after.
