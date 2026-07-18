# Job-Market LinkedIn-First and Login Retry Implementation Plan

**Date:** 2026-07-17

**Design:**
`docs/superpowers/specs/2026-07-17-job-market-linkedin-first-login-retry-design.md`

## Loop Contract

**Goal:** Deep/audit job-market runs proactively schedule LinkedIn, premature
login confirmation reopens normal Chrome within a bounded retry loop, and the
resulting source changes are pushed without generated research or private Git
metadata.

**Input scope:** Job-market packs, platform planning, authenticated-browser
request construction, login handoff, auth/loop records, documentation, tests,
`.gitignore`, and the unpushed commit range. Generated `output/` files and
personal browser state remain local.

**Execute:** Add depth-scoped pack platforms; route LinkedIn with advisory
noninteractive coverage; retry only `login_incomplete`; update UI/status metadata;
ignore generated output; test; smoke; scan; rewrite only unpushed Git identities;
push.

**Checks:** Focused routing/auth/loop tests, full pytest, Ruff, diff check, browser
doctor, public-only smoke, interactive LinkedIn smoke, staged-path audit,
content-secret scan, and author/committer scan for `origin/main..HEAD`.

**Feedback rules:** Routing regression -> repair shared effective-platform
selection; premature confirmation -> reopen within remaining budget; exhausted
attempts -> `login_incomplete`; noninteractive -> advisory coverage warning;
privacy hit -> stop before push and sanitize/ignore; live login remains incomplete
-> report the human gate without bypassing it.

**Records:** Existing plan, auth challenge, evidence quality, claim review, and
loop artifacts; tests; Git commits. Only sanitized attempt counts and coverage
status may enter artifacts.

**Stop conditions:** Success when all checks and push pass. Stop on real private
data, destructive published-history changes, failed safety tests, or an unresolved
human login gate.

**Human gates:** The user owns login/SSO/MFA/CAPTCHA. The user already approved
normal source commits and push after privacy checks. Published-history force push
is excluded without separate approval.

## Phase 1 — Depth-Scoped LinkedIn Routing

Files:

- `packs/job_market.json`
- `src/research_engine/default_packs/job_market.json`
- `src/research_engine/platforms.py`
- `src/research_engine/runner.py`
- focused pack/platform/runner tests

Steps:

1. Add `platforms_by_depth.deep/audit = ["linkedin"]` to both identical pack
   copies.
2. Add one small helper that combines legacy pack platforms with the selected
   research depth.
3. Pass research depth into platform planning and use the same effective set for
   browser request construction.
4. Mark pack-scheduled browser coverage advisory when the connector cannot open
   an interactive browser; explicit user-requested LinkedIn remains blocking.
5. Record advisory gaps separately from pending human actions and surface them as
   review-required coverage warnings.

Checks:

- deep/audit job-market plans include one LinkedIn browser source without the
  topic naming LinkedIn;
- quick omits it unless explicitly named;
- `browser-auth=never` produces no browser request;
- official job snapshot counting remains unchanged;
- project and packaged packs remain byte-equivalent JSON values.

## Phase 2 — Bounded Login Verification Retry

Files:

- `src/research_engine/connectors/authenticated_browser.py`
- `tests/test_authenticated_browser.py`

Steps:

1. Wrap the existing handoff/verification sequence in a maximum-three-attempt
   loop using one wall-clock deadline.
2. Pass the remaining timeout to each normal-Chrome handoff.
3. Retry only when Playwright still sees a login marker after a successful
   handoff; all other statuses stop immediately.
4. Update the confirmation copy to explain the close-for-verification behavior
   and display an incomplete-login notice on retries.
5. Record a sanitized `login_attempts` count without profile, process, cookie, or
   command data.

Checks:

- context close/handoff/reopen ordering is preserved for every attempt;
- attempt two and three may succeed;
- fourth handoff never starts;
- shared timeout is not reset;
- consent is shown once;
- cancellation and process/profile failures do not retry;
- guarded capture starts only after login markers disappear.

## Phase 3 — Privacy and Documentation

Files:

- `.gitignore`
- `README.md`
- `docs/connector-support.md`
- focused privacy/status tests if existing tests do not cover the rule

Steps:

1. Ignore `/output/`; do not delete the current local research output.
2. Document LinkedIn's discovery/trend role versus official ATS truth.
3. Document the verification close/reopen loop and noninteractive coverage
   behavior.
4. Ensure no generated report, browser profile, cookie/storage file, local
   callback token, or absolute profile path is staged.

## Phase 4 — Verification

Run:

```bash
/opt/homebrew/bin/python3.10 -m pytest -q \
  tests/test_market_profile.py tests/test_packs.py tests/test_runner.py \
  tests/test_authenticated_browser.py tests/test_loop.py
/opt/homebrew/bin/python3.10 -m pytest -q
/opt/homebrew/bin/python3.10 -m ruff check src tests
git diff --check
research-engine doctor browser --format json --no-write
research-engine run "public-only authorized-export smoke" \
  --browser-auth never --search-provider none \
  --external-evidence tests/fixtures/stripe_false_positive_evidence.jsonl \
  --output /tmp/research-engine-browser-smoke
```

Then run an interactive deep US job-market smoke that does not mention LinkedIn.
Verify that LinkedIn opens automatically, premature confirmation reopens Chrome,
successful login resumes guarded capture, official counts remain official-only,
and artifacts contain no private browser state.

## Phase 5 — Commit Identity, Privacy Scan, and Push

1. Wait until other local research work is no longer mutating the shared checkout.
2. Stage only explicit implementation files and commit with the repository
   owner's GitHub noreply identity.
3. Add `/output/` before staging so current job-market artifacts remain untracked
   and ignored.
4. Scan staged content and `origin/main..HEAD` for sensitive values, personal
   paths, emails, phones, auth headers, cookies, tokens, private keys, storage
   state, and browser profile data.
5. Rewrite author and committer metadata only for unpushed commits using the
   noreply identity; do not rewrite `origin/main`.
6. Re-run the identity and tree-equivalence checks after rewriting history.
7. Push `main` normally; never force-push published history in this task.

## Acceptance

- LinkedIn is automatic for deep/audit job-market research and not automatic for
  quick/public-only research.
- Noninteractive missing coverage is review-required, not silently omitted.
- Premature Continue causes a bounded retry instead of a terminal first failure.
- No simultaneous Playwright/normal-Chrome profile ownership occurs.
- LinkedIn evidence cannot count as a verified official opening.
- `/output/` and browser/session artifacts are absent from the pushed tree.
- Every newly pushed commit uses the GitHub noreply identity.
- Focused/full tests, lint, doctor, both smoke paths, privacy scans, and normal
  push pass.
