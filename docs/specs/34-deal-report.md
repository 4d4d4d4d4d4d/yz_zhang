# Spec 34 — Exportable Deal Readiness Report

**Status:** Accepted · **Depends on:** 11 (pipeline), 20 (registry), 27 (store), 33 (format)

## 1. Problem (critical analysis)

The platform's entire thesis is trust-building to *close* a cross-border deal
("增加互信，促成商业合作"). `TrustPipeline.vue` (spec 11) computes a rich
readiness verdict — but that verdict is **trapped inside the tool**. An
operator cannot hand the counterparty a summary; the buyer abroad, who cannot
visit the office, gets nothing portable. Every deal desk (DocuSign CLM,
Salesforce, PandaDoc) exports a one-pager. That export is the missing climax
of the whole trust journey.

## 2. Scope

- `logic/dealReport.js` — pure assembler. `buildDealReport(readiness, { now, id })`
  turns a pipeline `dealReadiness` result into a shareable structure: headline
  `verdict` (ready / blocked / progress), score, per-stage status
  (complete / partial / open) derived from `credits`, severity-ordered
  `blockers`, completion count, and an injected `generatedAt`. Imports nothing
  (spec 00 §2) — stages come from the readiness shape, not from `pipeline`.
- `store/workspace.js` — extract `dealReadinessSnapshot()` so the notification
  bell and this report run the **same** engine over the **same** workspace deal.
- `components/DealReportCard.vue` — a new `showcase/report` sub-tab. Renders the
  verdict, stages, and blockers; **Copy summary** writes a localized plain-text
  one-pager to the clipboard; **Print / PDF** uses `window.print()` behind a
  global print stylesheet that isolates the report from the console shell.
- Registry gains `showcase.report`; i18n adds the sub-tab label + a `report.*`
  block across all four locales (parity-enforced by `tests/i18n.test.js`).

## 3. Review record

**R1 — single-source verdict.** The report must never disagree with the bell.
Rather than recompute readiness, the readiness input is extracted into one
store helper both consumers call. A drift between "your deal is blocked"
(bell) and "ready to sign" (report) would be a credibility disaster.

**R2 — no domain import in the report.** `dealReport` derives stages from
`Object.keys(readiness.credits)` instead of importing `STAGES` from `pipeline`,
keeping the logic layer's zero-import rule (enforced by `architecture.test.js`).

**R3 — localization lives in the view, structure in the logic.** The assembler
emits stable enum keys (`verdict`, `status`, `severity`); the component maps
them to i18n. So the shareable text is localized without the logic layer ever
importing vue-i18n.

**R4 — print isolation via `visibility`.** A scoped print rule can't hide the
SPA shell. A single global `@media print` block (`body * { visibility: hidden }`
then reveal `.deal-report`) is layout-agnostic and robust, and the action
buttons are hidden from the printout.

## 4. Tests
`tests/dealReport.test.js`: verdict classification (hard-fail precedence),
credit→status mapping, blocker severity ordering (zero before half), the
ready-deal happy path, and defensiveness against empty readiness. The sub-tab's
render + wiring is covered by the existing mount-smoke sweep; i18n parity by
`tests/i18n.test.js`.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget, plus a browser smoke: the `showcase/report` tab renders a
verdict + score, "Copy summary" puts a localized one-pager on the clipboard.
