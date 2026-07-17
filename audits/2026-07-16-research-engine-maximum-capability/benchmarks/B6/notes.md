# B6 — Adversarial sources (JS-heavy, blocked, 404, DNS, PDF)

- Pack: audits/.../fixtures/packs/b6_adversarial.json (audit-only, via --pack-dir; repo packs untouched)
- Command: `... run "adversarial fetch degradation audit" --pack b6_adversarial --pack-dir <audit>/fixtures/packs --depth deep --source-timeout-seconds 30` (10.2s)
- Run dir: `runs/2026-07-16-adversarial-fetch-degradation-audit`
- Result: complete_with_warnings, 4 rows, exactly 1 warning.

## Probe-by-probe (5 designed failure modes)
| Probe | Detected? | What happened |
|---|---|---|
| DNS-invalid host | ✅ | ValueError warned, row excluded — only failure caught |
| X.com search (bot/login gate) | ❌ | Login-wall text ("Continue with phone / Google") captured via Playwright, `access_blocked: False`, `is_final_page: True`, quality tier **high** (0.72+) |
| Reddit search (block page) | ❌ | "You've been blocked by network security" stored as evidence, tier medium |
| 404 URL | ❌ | example.com placeholder text captured; **no HTTP status code exists anywhere in the row schema** — the engine cannot distinguish 200/404/500 |
| PDF URL | ❌ | **Raw PDF bytes** (`%PDF-1.5 %… /FlateDecode stream x…` mojibake) stored as 4000-char evidence text, tier **high** (length bonus rewards binary garbage) |

## Interpretation
- Failure detection = "exception thrown". Any 2xx-ish response with non-empty body — login walls, block pages, wrong content types, binary — is success.
- The bot-gate heuristic (4 substrings, web.py:132) missed both the X login wall and the Reddit block page phrasing.
- Content-type is never inspected; PDF/binary flows into text extraction unchecked.
- Quality scoring then *upgrades* the garbage (https + title + ≥240 chars ⇒ high tier).
- Run status honest only about the one thrown exception.

## Rubric
Failure transparency **1** (1/5 modes visible) · Extraction 0 (PDF binary) · Artifacts 5 · Latency 5 · others n/a per design.
Headline per plan rubric: **1/5** (silent acceptance of garbage across 4/5 probes).
