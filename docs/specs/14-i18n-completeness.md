# Spec 14 — Localization Completeness & Message Safety (出海 i18n)

Status: **Approved** · Review: R1 (2026-07-04) · Artifacts:
`i18n/locales/*` (console.tabs), `tests/i18n.test.js`

## Problem

Two gaps surfaced in v9:
1. A vue-i18n message with an unescaped `@` crashed the entire Contact
   page in all four locales — and only a widened smoke test caught it.
   Message safety must be a **unit test**, not a smoke-test lottery.
2. The console shell's sub-tab labels are hardcoded English. A buyer in
   Osaka opening the workspace sees localized section titles over
   English navigation — exactly the "translated, not local" impression
   the product warns against.

## Design

### Message-safety test (`tests/i18n.test.js`)
- **Key-tree parity**: `zh`, `ja`, `es` must carry exactly the key tree
  of `en` — no missing keys (falls back to English silently), no extra
  keys (dead weight drifting out of sync).
- **Compile safety**: every message in every locale is compiled through
  `@intlify/message-compiler` (`baseCompile` with an `onError` collector).
  A message with errors (unescaped `@`, malformed `{}` interpolation,
  stray plural `|`) fails the suite with locale + key in the assertion
  message. This is the executable regression guard for the v9 Contact
  crash. *(R1 amendment: the draft ran `t()` through `createI18n`, but
  the dev-mode runtime only warns on bad messages — production throws —
  so the runtime check passed on known-bad input. The compiler-direct
  check reports errors deterministically in every environment.)*
- **Shell coverage**: `console.s.<key>` and `console.tabs.<key>.*` must
  exist for every section registered in `Console.vue` (section list
  mirrored as a fixture; drift fails the test).

### Localized sub-tabs
- `Console.vue` section registry drops hardcoded `label` strings; labels
  resolve via `t('console.tabs.<section>.<sub>')`.
- All 38 sub-tab labels translated for en / zh / ja / es. Domain terms
  that function as product nouns (ZOPA, DPIA, DSR, A/B) stay untranslated
  per glossary practice (spec 08's keep-terms, applied editorially).

## Guarantees
- Adding a section/sub without translations fails CI (shell-coverage
  assertion), so the console can never silently grow English-only chrome.

## Test plan
- Parity: inject a missing key into a copy of zh → test fails naming it.
  (Verified during development; the shipped assertion runs on the real
  catalogs.)
- Compile: the pre-fix `partners@adforge.ai` form fails the compile
  check; the escaped `{'@'}` form passes.
- Shell: every registry section key present in `console.s` and
  `console.tabs` across all locales.

## Review record — R1
- ✅ Compile-through-real-runtime chosen over regex linting (regex can't
  track vue-i18n's actual grammar; the runtime is the source of truth).
- ✅ Extra-key check kept despite noise risk — catalogs drifting apart is
  the failure mode that hurts at translation-vendor handoff.
- Verdict: **approved**.
