# Research Report: AI inference market landscape

- Pack: `market_landscape`
- Raw rows: `14`
- Stance: `evidence_collected_needs_analysis`
- Confidence: `medium`
- Action bias: `analyze_before_action`
- Average evidence quality: `0.64`
- Duplicate clusters: `7`
- Conflict flags: `0`

## Evidence
- [market_definition official evidence](https://fixture-market_definition.example/report) - quality `medium` duplicate
- [companies_products official evidence](https://fixture-companies_products.example/report) - quality `medium` duplicate
- [pricing official evidence](https://fixture-pricing.example/report) - quality `medium` duplicate
- [demand official evidence](https://fixture-demand.example/report) - quality `medium` duplicate
- [competition official evidence](https://fixture-competition.example/report) - quality `medium` duplicate
- [constraints official evidence](https://fixture-constraints.example/report) - quality `medium` duplicate
- [contrary_evidence official evidence](https://fixture-contrary_evidence.example/report) - quality `medium` duplicate
- [market_definition official evidence](https://fixture-market_definition.example/report) - quality `medium`
- [companies_products official evidence](https://fixture-companies_products.example/report) - quality `medium`
- [pricing official evidence](https://fixture-pricing.example/report) - quality `medium`
- [demand official evidence](https://fixture-demand.example/report) - quality `medium`
- [competition official evidence](https://fixture-competition.example/report) - quality `medium`
- [constraints official evidence](https://fixture-constraints.example/report) - quality `medium`
- [contrary_evidence official evidence](https://fixture-contrary_evidence.example/report) - quality `medium`

## Evidence Quality Warnings
- 7 discovery-only evidence row(s) excluded from claims.
- 7 duplicate evidence row(s) detected across 7 cluster(s).

## Loop Status
- Loop status: `complete_with_review_required`
- Stop reason: `completed_with_review_required`
- Feedback actions:
  - `stop_brakes`: Set --source-timeout-seconds so long-running connectors have a hard stop.
  - `bounded_execution`: Set --source-timeout-seconds for fragile or long-running connectors.
  - `duplicate_pressure`: Review duplicate clusters before counting corroboration.
  - `claim_grounding`: Add claim specs or run a human/LLM analysis pass before treating this as decision-ready.
