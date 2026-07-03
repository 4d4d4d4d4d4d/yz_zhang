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

Capability flow across domains:

```
recommend (01) ──► marketing (02) ──► showcase evidence (06,07)
matchmaking (03) ──► meetings & tours (08,09) ──► field verification (10)
        └──────────► negotiation (04) ◄── compliance gates (05)
                              │
                    trust pipeline (11): evidence → verification →
                    compliance → commercial → READY TO SIGN
```
