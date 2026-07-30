# Spec 40 — Trust-Link Least-Privilege, Enforced on Read

**Status:** Accepted · **Depends on:** 06 (showcase / trust links)

## 1. Problem (critical analysis)

The product promises "**scoped, expiring trust links**" everywhere, and
`createTrustLink` records `scopes` + `watermark`. But nothing **applied** those
scopes: no function turned a link + the full reel data into the recipient's
redacted view. "Least privilege" was declared at creation and never enforced at
read — the security-critical half was missing, and the console never showed the
counterparty's actual view, so the whole mechanism was unverifiable.

## 2. Scope

- `logic/showcase.js` — `resolveTrustLinkView(link, reels, now)`:
  - runs `validateTrustLink`; an invalid/expired/revoked link returns
    `{ ok:false, reason }` and exposes **nothing**;
  - filters reels to `link.reelIds`;
  - projects each reel to **only** the fields the scopes permit — `assets`
    (with the link's watermark flag), `metrics`, `provenance`, `pricing`. A
    field outside scope is *omitted from the object*, not merely hidden.
- `TrustLinkBuilder.vue` — reels carry the full field set; a new **Recipient
  preview** panel renders `resolveTrustLinkView` for the newest link, showing
  exactly what the counterparty sees and what is hidden by scope — closing the
  create-without-consume loop (per the spec-30 lesson).

## 3. Review record

**R1 — omit, don't hide.** Out-of-scope fields are absent from the returned
object, so a UI bug can't accidentally render something the scope forbids. The
enforcement lives in the pure function, not the template.

**R2 — identity always visible.** `id`/`title` are always returned: the
recipient must know *what* was shared with them; the sensitive payload
(assets/metrics/provenance/pricing) is what the scopes gate.

**R3 — fail closed.** Any validation failure yields `ok:false` with no reels,
mirroring `validateTrustLink`; a malformed/expired/revoked link can never leak.

## 4. Tests
`tests/showcase.test.js` (extended): only scoped fields present (others
absent), watermark flag on assets, reel-id filtering, expired/revoked → no
exposure, and tolerance of missing fields / non-array input. Component wiring
covered by mount-smoke.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: a metrics-only link's preview shows metrics and
lists assets/provenance/pricing as hidden.
