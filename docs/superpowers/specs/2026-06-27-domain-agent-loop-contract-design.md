# Domain Agent Loop Contract Design

Date: 2026-06-27
Status: Approved design
Owner: Research Engine

## Summary

Research Engine should be the reusable evidence layer for domain agents, not a
separate workflow agent for every industry. Insurance, medical billing, legal,
financial compliance, procurement, sales operations, customer support, and code
migration agents can all call the same research loop when they need outside
facts, policy text, market signals, forum evidence, vendor documentation, or
regulatory material.

The common contract is:

```text
domain request -> research scope -> focused connector plan -> evidence artifacts
-> independent checks -> loop stop reason -> domain agent decision gate
```

The domain agent owns its business workflow. Research Engine owns evidence
collection, normalization, source quality, conflict checks, claim grounding, and
stop conditions before any LLM or domain agent treats the material as reliable.

## Loop Engineering Requirements

Every run must enforce four loop requirements.

### 1. Keep Context Clean

- Raw rows go to artifacts such as `evidence.jsonl`, not directly into an LLM
  prompt.
- Reports and manifests carry compact summaries, quality scores, and artifact
  references.
- Large, messy platform captures should enter through `external_jsonl` or a
  connector artifact, then be normalized and capped before synthesis.
- Local paths, cookies, tokens, authorization headers, and command-like secrets
  remain redacted or excluded from artifacts.

### 2. Know When To Stop

- The runner must carry explicit worker, retry, timeout, and per-source result
  limits.
- `failed_no_sources`, `failed_no_rows`, and critical check failures stop the
  run before synthesis.
- Warnings do not disappear. They become feedback actions and mark the run as
  review-required.
- A terminal command ending is not success. Only the loop record's status and
  stop reason decide whether the run is usable.

### 3. Use A Critic That Can Say No

- Collection/maker work and checker/critic work must remain separate.
- Source quality, duplicate pressure, conflict review, claim grounding, and
  connector health are recorded as independent checks.
- Generic evidence is not automatically decision-ready. A domain pack needs
  claim specs, or the run must stop with a human/LLM analysis requirement.
- Critical domains must add pack-specific checks before downstream actions.

### 4. Use Focused Tools

- A run should use a small, explicit, non-overlapping connector set.
- Repeated source IDs, overly broad connector plans, missing upstream tools, or
  auth-expired collectors should be visible as warnings or failures.
- Connectors must be read-oriented and safe to rerun. Mutating account actions,
  uploads, payments, messages, deletion, and external side effects are outside
  Research Engine's core loop.

## Domain Agent Integration Matrix

| Domain agent | Research Engine role | Typical evidence sources | Critic checks | Human gate |
| --- | --- | --- | --- | --- |
| Insurance claims | Gather policy language, repair estimates, weather/event evidence, precedent summaries | Insurer docs, public weather/event data, repair/vendor docs, authorized claim exports | Policy term grounding, source date freshness, conflict flags | Claim denial, payout recommendation, customer communication |
| Medical billing/coding | Gather payer policy, CPT/ICD guidance, LCD/NCD references, denial patterns | CMS, payer manuals, coding references, authorized EHR/billing exports | Regulatory source priority, code-policy mapping, stale policy warning | Final coding, appeal filing, patient/account update |
| Legal discovery/contract | Gather clause examples, public filings, case/regulatory context, authorized document exports | Court/regulatory sites, contract repositories, firm knowledge exports | Jurisdiction/source tier, privilege/private-data boundary, conflict review | Legal advice, production decisions, filings, signatures |
| Financial compliance | Gather rules, enforcement actions, broker/exchange guidance, surveillance evidence | SEC/FINRA/CFTC, exchange rules, company policies, authorized surveillance exports | Primary-source requirement, rule-date freshness, no-trade-action gate | Filing, client communication, trade restriction, escalation closure |
| Procurement/supply chain | Gather supplier news, lead times, capacity, pricing, quality issues, logistics risk | Supplier sites, filings, shipping data, forums, authorized vendor portals | Source diversity, date freshness, conflict review, supplier claim grounding | Purchase order, vendor onboarding/offboarding, contract terms |
| Sales operations | Gather account news, hiring/product signals, competitive signals, CRM exports | Company sites, LinkedIn exports, job posts, reviews, CRM data | Signal-source mapping, duplicate pressure, stale lead warning | Outreach send, CRM mutation, offer/discount decision |
| Customer support QA | Gather policy docs, ticket samples, release notes, public incident data | Help center, changelogs, authorized ticket exports, forums | Policy grounding, customer-data redaction, incident timeline consistency | Customer reply, refund/credit, account mutation |
| Code migration/testing | Gather upstream docs, API changes, issue reports, migration examples, repo evidence | GitHub, official docs, changelogs, package registries, CI logs | Version/date grounding, repro evidence, test-failure evidence | Production deploy, destructive migration, credential or infra changes |

## Runtime Acceptance

A Research Engine run is acceptable as a domain-agent input only when:

- `loop_record.json` exists.
- `loop_status` is `complete` or intentionally accepted as
  `complete_with_review_required`.
- No check with status `fail` is present.
- Context hygiene, stop brakes, critic separation, and tool focus checks are
  present in `check_results`.
- Domain-specific high-risk actions remain behind human gates.

## Non-Goals

- Do not make Research Engine a generic autonomous workflow runner.
- Do not bypass login walls, paywalls, robots controls, rate limits, or platform
  terms.
- Do not store cookies, session tokens, broker entitlements, protected health
  information, privileged legal material, or customer secrets in repo artifacts.
- Do not let Research Engine send messages, make payments, submit claims,
  file legal documents, place trades, update accounts, or deploy code.

## Implementation Notes

The first implementation step is deterministic:

- Add runtime checks for context hygiene, stop brakes, critic separation, and
  tool focus.
- Keep existing CLI and artifact names stable.
- Add tests that prove generic evidence is review-required and that broad or
  duplicate tool plans are visible to downstream agents.
- Document the domain-agent contract in README so users understand the product
  boundary.
