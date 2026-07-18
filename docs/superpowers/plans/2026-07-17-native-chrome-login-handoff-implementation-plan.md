# Native Chrome Login Handoff Implementation Plan

**Date:** 2026-07-17

**Design:**
`docs/superpowers/specs/2026-07-17-native-chrome-login-handoff-design.md`

## Loop Contract

**Goal:** Google/enterprise OAuth login succeeds in a normal, dedicated Chrome
profile, then the existing Playwright read-only collector resumes without
receiving credentials or attaching to a personal profile.

**Input scope:** Existing authenticated-browser connector, dedicated profile,
approved recipe URL, browser doctor, challenge artifacts, and tests. No stealth,
personal Chrome profile, extension, proxy, or login automation.

**Execute:** Resolve normal Chrome; close Playwright before login; launch Chrome
with the dedicated profile; wait for explicit completion on a nonce-protected
loopback page; reopen Playwright; verify authentication; run the existing request
guard and extractor.

**Checks:** Unit tests for resolution/argv/status mapping; focused connector and
doctor tests; full suite; Ruff; browser doctor; public-only smoke; one
user-operated LinkedIn Google OAuth smoke; artifact secret scan.

**Feedback rules:** Missing Chrome -> deterministic setup status; timeout -> stop
at human gate; profile lock -> bounded wait then stop; login marker remains ->
`login_incomplete`; test regression -> preserve existing consent/public-only
behavior before retrying.

**Records:** Existing `auth_challenges.jsonl`, `collection_execution.json`,
`query_plan.json`, and `loop_record.json`. No new artifact type.

**Stop conditions:** Success when LinkedIn collects at most three visible rows
and artifacts are clean. Stop and report on user timeout, unavailable Chrome,
incomplete login, or policy/safety failure.

**Human gate:** The user owns consent, OAuth/SSO/MFA/CAPTCHA, and the explicit
**I’m signed in — continue** confirmation.

## Phase 1 — Native Browser Handoff

Modify only `src/research_engine/connectors/authenticated_browser.py` and its
existing test file.

- Add stdlib Chrome executable resolution with one optional environment override.
- Reject Chrome for Testing and Playwright-managed executables for login.
- Launch an argv list with no shell, remote debugging, CDP, or automation flags.
- Serve a nonce-protected, loopback-only completion/cancel page with no logs.
- Wait five minutes, terminate only the process created by the handoff on
  completion or timeout, and verify the dedicated profile lock is released.
- Return narrow statuses: `ready`, `login_browser_unavailable`,
  `login_browser_timeout`, `login_browser_failed`, `login_cancelled`, or
  `profile_lock_timeout`.

## Phase 2 — Playwright Resume

- Keep the current consent context.
- Detect a login wall, close the context, and invoke the handoff.
- Reopen the same profile after successful handoff.
- Navigate to the original target and return `login_incomplete` if login markers
  remain.
- Install the existing request guard only for the automated capture phase.
- Preserve current consent, sanitation, budgets, recipes, and normalized rows.

## Phase 3 — Doctor and Documentation

- Add a `browser:login_chrome` doctor check using the shared resolver.
- Document ordinary-Chrome login handoff, the browser confirmation signal,
  environment override, and failure statuses.
- Keep the CLI surface unchanged.

## Phase 4 — Verification

```bash
/opt/homebrew/bin/python3.10 -m pytest -q tests/test_authenticated_browser.py \
  tests/test_doctor.py tests/test_runner.py tests/test_loop.py
/opt/homebrew/bin/python3.10 -m pytest -q
/opt/homebrew/bin/python3.10 -m ruff check src tests
git diff --check
research-engine doctor browser --format json --no-write
research-engine run "public-only authorized-export smoke" --browser-auth never \
  --search-provider none \
  --external-evidence tests/fixtures/stripe_false_positive_evidence.jsonl \
  --output /tmp/research-engine-browser-smoke
```

Then run the user-operated LinkedIn smoke. The user approves, signs in through
normal Chrome, clicks **I’m signed in — continue**, and Playwright resumes.
Inspect the run artifacts for credentials, cookies, tokens, profile paths, and
command lines before delivery.

## Acceptance

- Google OAuth is never opened in an automation-capable login browser.
- Playwright and normal Chrome never hold the dedicated profile concurrently.
- Existing noninteractive and `--browser-auth never` behavior is unchanged.
- All new failure paths are bounded, explicit, and artifact-safe.
- Full tests and lint pass.
- LinkedIn live smoke completes or remains the sole recorded human/external gate.
