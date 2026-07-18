# Generic Authenticated Browser Crawler Implementation Plan

**Date:** 2026-07-17

**Design:** `docs/superpowers/specs/2026-07-17-generic-authenticated-browser-crawler-design.md`

## Goal

Ship a generic, consented, read-only Playwright recovery phase that turns
recoverable login barriers into an auditable human gate, resumes the same research
run, and includes fixture-verified recipes for the approved ten sites.

## Baseline

- Commit before implementation: `95a24bb`
- Correct interpreter: `/opt/homebrew/bin/python3.10`
- Baseline suite: `276 passed in 11.53s`
- Plain `pytest` resolves to the macOS Command Line Tools Python 3.9 and cannot
  import the package; all implementation checks use `python3.10 -m pytest`.
- Worktree was clean before this plan.

## Execution Rules

- Keep Playwright optional; public-only behavior must remain available without it.
- Reuse `CollectionRequest`, `CollectionResult`, current content-validity checks,
  security redaction, execution reports, and loop artifacts.
- Use stdlib JSON, filesystem, HTML escaping, URL parsing, and atomic replacement.
- Do not add Browser Use, OpenCLI, a web framework, a native GUI toolkit, or a
  second evidence model.
- Do not automate login or CAPTCHA and do not save screenshots, traces, HAR,
  storage state, cookies, or headers.
- Browser recovery must be serial and bounded.
- A failed safety check maps to a deterministic stop; it never triggers creative
  retries.

## Phase 1 — Core Contracts and Recipes

### Create

- `src/research_engine/browser_auth.py`
- `src/research_engine/browser_recipes.py`
- `tests/test_browser_auth.py`
- `tests/test_browser_recipes.py`
- `tests/fixtures/browser_recipe_pages.json`

### Implement

- serializable auth challenge creation and redaction;
- owner-only, atomic remembered-consent store with list/revoke;
- exact-origin matching and recipe-version invalidation;
- capture-policy action/method checks and bounded crawl settings;
- one compact recipe data model, generic fallback, and ten approved definitions;
- search URLs, login markers, item/field selectors, safe pagination, mutation
  labels, and read-only request allowlists.

### Checks

- consent persistence/revoke/version tests;
- no broad-domain grant inheritance;
- dangerous action and unknown write request denial;
- one fixture contract per recipe;
- stable recipe registry and search URL generation.

## Phase 2 — Optional Playwright Connector

### Create

- `src/research_engine/connectors/authenticated_browser.py`
- `tests/test_authenticated_browser.py`

### Modify

- `src/research_engine/connectors/__init__.py`
- `pyproject.toml`

### Implement

- optional `browser` dependency extra;
- visible site-specific persistent context;
- static consent document via `page.set_content`;
- user-controlled login wait with no capture/logging;
- capture-mode request guard, bounded scrolling/pagination, extraction, dedupe,
  and normalized rows;
- injectable browser flow for deterministic tests;
- honest statuses for unavailable browser, denial, login timeout, recipe drift,
  rate limit, mutation, and sensitive output.

### Checks

- fake-browser consent/login/capture paths;
- denied and noninteractive paths never launch login;
- one remembered grant skips repeat consent;
- capture rows preserve source/query/facet/pass metadata;
- no sensitive browser state enters the result.

## Phase 3 — Runner, Artifacts, CLI, and Doctor

### Modify

- `src/research_engine/runner.py`
- `src/research_engine/cli.py`
- `src/research_engine/interactive.py`
- `src/research_engine/doctor.py`
- `src/research_engine/loop.py`
- related tests

### Implement

- `browser_auth="auto"|"never"` runner/CLI mode;
- recovery request construction from recoverable invalid rows and explicitly
  requested/login-required platform plans;
- serialized second execution phase and report merge;
- `auth_challenges.jsonl` and collection-mode/status metadata;
- `research-engine auth list|revoke|clear-profile` with narrow target resolution;
- doctor checks for package, Chromium executable, and GUI/interaction readiness;
- wizard summary of browser-auth behavior.

### Checks

- public-only default compatibility and `--browser-auth never`;
- noninteractive `auto` records human action required and never hangs;
- login/robots/paywall classification does not broaden access;
- CLI revoke/clear affects only the selected site;
- loop records retain explicit human gates and stop reasons.

## Phase 4 — Recipe Verification and Documentation

### Modify

- `docs/connector-support.md`
- `README.md`
- recipe fixture and contract tests

### Implement

- LinkedIn, X, Reddit, Blind, Glassdoor, Indeed, OnePointThreeAcres, Hacker News,
  GitHub, and Stack Overflow recipe definitions;
- fixture verification state and honest `live_verified` state;
- setup, consent, revoke, profile-clear, headless degradation, and safety docs.

### Checks

- all ten fixtures extract at least one normalized text row;
- selectors or fixture fields missing from a recipe report `recipe_drift`;
- YouTube stays transcript-only and outside the authenticated recipe batch.

## Phase 5 — Verification Loop

Run, repair, and rerun:

```bash
/opt/homebrew/bin/python3.10 -m pytest -q tests/test_browser_auth.py \
  tests/test_browser_recipes.py tests/test_authenticated_browser.py
/opt/homebrew/bin/python3.10 -m pytest -q tests/test_runner.py \
  tests/test_doctor.py tests/test_interactive.py tests/test_loop.py
/opt/homebrew/bin/python3.10 -m pytest -q
/opt/homebrew/bin/python3.10 -m ruff check src tests
git diff --check
research-engine doctor browser --format json --no-write
research-engine run "public-only crawler smoke" --browser-auth never \
  --search-provider none --output /tmp/research-engine-browser-smoke
```

Feedback rules:

- focused failure -> repair the owning boundary and rerun focused tests;
- regression -> preserve old API/artifact behavior before continuing;
- secret leakage -> block delivery until the row/artifact path is fixed;
- browser unavailable -> verify honest degradation, not test bypass;
- recipe drift -> keep the recipe unverified and record the exact missing contract;
- live platform challenge -> stop at the human gate.

## Phase 6 — LinkedIn Human Gate

After all deterministic checks pass, request explicit user authorization for one
live LinkedIn read-only smoke. The feature itself must display consent, let the
user log in, collect at most three visible rows, perform no mutation, and scan the
run artifacts for sensitive data.

Do not mark the complete design objective achieved until either:

- the authorized smoke passes; or
- the user declines/unavailable account is reported as the remaining human gate.

## Acceptance

- Recoverable barriers become challenges, not evidence.
- Consent and login resume the same run when interaction is available.
- Public-only/noninteractive runs never hang.
- Mutation and secret gates are deterministic and tested.
- Ten recipes pass offline fixture contracts.
- Full tests and lint pass.
- LinkedIn live smoke passes with user authorization or is the sole reported human
  gate.
