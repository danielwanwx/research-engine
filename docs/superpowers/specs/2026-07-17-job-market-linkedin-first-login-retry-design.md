# Job-Market LinkedIn-First and Login Retry Design

**Date:** 2026-07-17

**Status:** Approved and implemented

## Problem

The `job_market` research pack currently treats official careers/ATS pages and
public web search as its default sources. LinkedIn has a supported authenticated
browser recipe, but it is only scheduled when the topic explicitly names
LinkedIn or another collected page exposes a recoverable login barrier. A normal
job-market topic therefore does not proactively collect LinkedIn hiring posts,
recruiter signals, or role-language changes.

The native Chrome login handoff has a second usability defect. Clicking
**I’m signed in — continue** intentionally closes the dedicated Chrome process
so Playwright can acquire the same profile. When the user confirms too early,
Playwright returns `login_incomplete` and the handoff ends. The close is required
for profile safety, but the terminal failure makes the workflow feel as if the
browser unexpectedly disappeared.

Generated research files under `output/` are also not ignored today. The current
untracked job-market scope files contain no personal information, but future
research output may include user-specific targeting details and must not be
committed accidentally.

## Decision

Implement two related, bounded changes:

1. Deep and audit `job_market` runs proactively schedule LinkedIn as a required
   supplemental discovery/trend source when `--browser-auth auto` is enabled.
2. An incomplete login re-enters the normal-Chrome handoff instead of ending
   immediately, subject to three attempts and the existing five-minute total
   login budget.

Official company careers pages and official ATS endpoints remain the source of
truth for whether a position is open. LinkedIn is primary for discovery, hiring
manager/recruiter signals, title vocabulary, and skill-demand changes; it does
not independently authorize quantitative active-opening claims.

Quick runs do not proactively schedule LinkedIn. Noninteractive runs may finish
the public/official portion, but must record missing LinkedIn coverage, keep
confidence at or below medium, and expose a clear interactive follow-up action.

## Approaches Considered

### Selected: declarative pack priority plus bounded verification retry

The packaged and project `job_market` packs declare LinkedIn for deep/audit
depths. Shared platform planning resolves the depth-specific pack platforms, and
the existing browser-auth request builder schedules the recipe. Login retry stays
inside the existing authenticated-browser flow, where profile ownership already
lives.

This keeps job-market source policy in the pack, avoids prompt-only behavior, and
fixes the handoff once for every recipe without adding a new browser dependency.

### Rejected: hard-code LinkedIn directly in the runner

This is a smaller local edit but mixes one domain policy into orchestration and
makes later pack-specific platform priorities harder to express or test.

### Rejected: inspect normal Chrome through CDP while it remains open

CDP, remote debugging, or injected automation would recreate the authentication
compatibility and trust problems that the native handoff was designed to avoid.

## Source Routing

The job-market pack gains a depth-scoped platform declaration equivalent to:

```json
{
  "platforms_by_depth": {
    "deep": ["linkedin"],
    "audit": ["linkedin"]
  }
}
```

Platform planning accepts the research depth separately from the existing
platform-scope selector. A small shared helper resolves the effective pack
platform set. Both the platform plan and authenticated-browser request builder
use that same set so artifacts match execution.

Behavior by mode:

| Run | LinkedIn behavior |
| --- | --- |
| `job_market`, `deep`/`audit`, `browser-auth=auto`, interactive | Proactively open exact-origin consent/login and collect bounded LinkedIn rows. |
| `job_market`, `deep`/`audit`, noninteractive | Complete public/official collection, record advisory LinkedIn coverage gap, and request an interactive follow-up. |
| `job_market`, `quick` | Do not proactively add LinkedIn; explicit topic mentions still retain existing behavior. |
| `browser-auth=never` | Never open LinkedIn; record public-only policy in the plan without an auth challenge. |
| Other research packs | Preserve current routing unless their own pack declares a platform. |

LinkedIn evidence uses its existing `user_consented_browser` access mode and is
kept separate from `official_job_posting` rows. Job-market snapshots continue to
count only final, verified official postings.

## Login Verification Retry

The profile ownership sequence remains strict:

```text
Playwright detects login wall
  -> Playwright closes profile
  -> normal Chrome opens target + local confirmation tab
  -> user confirms login completion
  -> normal Chrome closes and releases profile
  -> Playwright verifies target
     -> authenticated: install guard and capture
     -> still login wall: close Playwright and reopen normal Chrome
```

The confirmation button becomes **完成登录并开始验证** / **Verify sign-in and
continue**. Its page explains that the dedicated Chrome window will close during
verification and may reopen if login is incomplete.

The retry loop has these limits:

- at most three normal-Chrome login attempts;
- one five-minute wall-clock budget shared by all attempts;
- no repeated origin-consent prompt after the first grant;
- no simultaneous normal Chrome and Playwright ownership of the profile;
- cancellation, missing Chrome, process failure, timeout, or profile-lock
  timeout stops immediately;
- only `login_incomplete` is retryable.

Each retry returns to normal Chrome with a visible message that the site still
showed a login wall. After the third incomplete verification, the existing
`login_incomplete` terminal status is recorded with zero authenticated rows.

## Noninteractive and Confidence Semantics

A pack-scheduled LinkedIn request carries an advisory coverage policy. When the
connector cannot open a browser because the run is noninteractive, the public
and official job-market report is still written. The auth challenge remains
visible, but the loop records a review-required coverage warning rather than
treating the entire evidence bundle as unusable.

The claim review adds a `linkedin_coverage` risk flag and cannot report confidence
above `medium` while required deep/audit LinkedIn coverage is missing. Interactive
login failures remain explicit human gates because the user already entered the
handoff and can resume it.

## Privacy and Git Safety

The implementation does not change the existing rule that browser credentials,
cookies, OAuth tokens, storage state, screenshots, traces, HAR files, and command
lines are excluded from run artifacts.

Add `/output/` to `.gitignore` so new research reports, scope files, and
user-specific market targeting are not accidentally staged. Existing tracked
files remain unchanged unless a privacy scan finds actual personal data. The
currently tracked job-market PDF is already present on the remote branch; its
metadata names `Research Engine`, and text/metadata scans found no personal
identifier, local path, email, phone number, credential, or browser state, so no
rollback is required.

Before pushing, the delivery loop must:

1. stage only explicit source, test, pack, documentation, and `.gitignore` paths;
2. verify no `output/`, run bundle, browser profile, storage-state, cookie, header,
   or environment file is newly tracked;
3. scan both the staged diff and `origin/main..HEAD` for home-directory paths,
   personal email/phone patterns, authorization headers, cookies, tokens, and
   private-key markers;
4. distinguish deliberately fake security-test fixtures from real values;
5. stop before push if any real private value is found, unstage/sanitize it, add
   the containing artifact class to ignore rules, and rerun the scan;
6. if an actual credential is ever found on the remote, revoke/rotate it before
   removing it from Git history.

The privacy scan also covers Git author and committer metadata. The repository's
existing commits ahead of `origin/main` use an automatically generated local-host
address. Before the next push, configure this repository to use the owner's
GitHub noreply address and rewrite only the unpushed commit range so the local
hostname is not added to more remote history. Verify that every commit in
`origin/main..HEAD` uses the noreply identity before pushing.

Older commits on `origin/main` already contain the local address. Removing it
requires rewriting published history and force-pushing, which may disrupt other
clones and is therefore a separate destructive action requiring explicit user
approval. `.gitignore` cannot remove commit metadata. This implementation will
not force-push historical commits implicitly.

No generated employment report or private browser state is part of the planned
commit.

## Loop Contract

**Goal:** Deep/audit US job-market research consistently collects LinkedIn trend
signals when authorized, retries premature login confirmation safely, and never
pushes personal research or browser state.

**Input scope:** Job-market pack configuration, platform planning, authenticated
browser handoff, loop/auth artifacts, tests, `.gitignore`, and current committed
source changes. Personal/default Chrome profiles and generated `output/` data are
out of scope.

**Execute:** Resolve depth-scoped pack platforms; collect public/official sources;
enter the LinkedIn human gate; retry only incomplete verification; normalize
authorized rows; record coverage; run privacy checks; commit and push explicit
code paths.

**Checks:** Pack/platform routing tests, quick/deep/audit mode tests, noninteractive
coverage behavior, three-attempt retry tests, total-budget tests, profile-close
ordering tests, full suite, Ruff, browser doctor, public-only smoke, interactive
LinkedIn smoke, staged-diff scan, remote-range privacy scan, and unpushed commit
identity verification.

**Feedback rules:** Missing login -> reopen normal Chrome within budget; third
incomplete attempt -> stop with `login_incomplete`; noninteractive -> retain
public report with review-required coverage gap; privacy hit -> stop, sanitize,
ignore, and rescan; regression -> preserve current public-only and consent
behavior before retrying.

**Records:** Existing `query_plan.json`, `auth_challenges.jsonl`,
`collection_execution.json`, `evidence_quality.json`, `claim_review.json`, and
`loop_record.json`. Retry attempt counts and coverage policy are sanitized scalar
metadata only.

**Stop conditions:** Success when routing, retry, privacy, full tests, and live
smoke pass. Stop for user cancellation, exhausted login budget, unsupported
browser, profile lock, real privacy finding, or a failed safety check.

**Human gates:** Exact-origin consent, login/SSO/MFA/CAPTCHA, final spec approval,
and push authorization. The user has already authorized a post-implementation
push subject to the privacy checks in this design.

## Testing and Acceptance

Acceptance requires:

1. a deep/audit `job_market` topic that does not name LinkedIn still plans exactly
   one LinkedIn authenticated-browser request;
2. a quick run does not add that request unless the topic explicitly names
   LinkedIn;
3. `--browser-auth never` never launches the browser;
4. noninteractive deep/audit runs retain public evidence and record missing
   LinkedIn coverage with confidence no higher than medium;
5. a premature confirmation closes normal Chrome, detects the remaining login
   wall, and reopens normal Chrome without a second consent prompt;
6. successful verification on attempt two or three proceeds to the existing
   guarded capture;
7. three incomplete verifications or the shared timeout stop with zero
   authenticated rows;
8. normal Chrome and Playwright never hold the profile concurrently;
9. official job counts remain based only on verified official final pages;
10. `output/` is ignored and no private artifact is added to the commit;
11. every unpushed commit uses the GitHub noreply identity and no unpushed commit
    exposes a local hostname;
12. focused tests, the full suite, Ruff, doctor, public-only smoke, interactive
    LinkedIn smoke, and privacy scans pass before push.

## Non-Goals

- Treating LinkedIn postings as official active-opening truth.
- Automating credentials, SSO, MFA, or CAPTCHA.
- Attaching to the user's personal/default Chrome profile.
- Keeping normal Chrome open while Playwright verifies the same profile.
- Making LinkedIn mandatory for quick or strict public-only runs.
- Uploading generated research reports or user-specific scope files.
