# Generic Authenticated Browser Crawler Design

**Date:** 2026-07-17

**Status:** Approved and implemented
**Decision:** Add a bounded, consented, read-only Playwright collection phase with
site-specific recipes and a generic DOM fallback. Keep public connectors as the
first path and preserve current evidence-quality gates.

## Problem

Research Engine can detect login walls, CAPTCHA pages, JavaScript shells, robots
denials, and other invalid bodies, but it cannot recover from a legitimate login
requirement inside the same research run. Its Playwright fallback is headless and
ephemeral, the planned browser sampler is not implemented, and authenticated
evidence must currently be captured elsewhere and imported through JSONL.

This causes two product failures:

1. public collection stops at content the user is authorized to view; and
2. complex JavaScript sites lack a bounded crawler that can search, scroll,
   paginate, extract structured rows, and resume the original query/facet.

The solution must not weaken the current rule that login walls, block pages,
paywalls, and other invalid content cannot support claims.

## Goals

- Detect a recoverable authentication barrier after public collection.
- Ask for informed user consent only when a specific site is needed.
- Let the user personally complete login, SSO, MFA, or CAPTCHA in a visible
  dedicated browser profile.
- Resume the same research run after login without losing query, facet, pass, or
  source provenance.
- Crawl authenticated pages within the existing `quick`, `deep`, and `audit`
  budgets.
- Prevent account mutation while allowing explicitly verified read-only browser
  operations, including narrowly allowlisted read-only GraphQL POST requests.
- Ship recipes for ten approved North American technology, career, and community
  sources, with a generic same-origin DOM fallback.
- Keep credentials, cookies, browser profiles, login DOM, screenshots, HAR files,
  and request headers out of research artifacts and Git.
- Degrade honestly when no browser, GUI, consent, login, or entitlement is
  available.

## Non-goals

- Bypassing paywalls, robots decisions, platform automation controls, rate limits,
  account entitlements, or organization access policy.
- Automating password, SSO, MFA, or CAPTCHA entry.
- Using stealth browsers, proxies, fingerprint evasion, or CAPTCHA-solving
  services.
- Posting, commenting, reacting, liking, following, connecting, messaging,
  applying, purchasing, uploading, deleting, or changing account settings.
- Making Browser Use, OpenCLI, a Chrome extension, or the user's daily Chrome
  profile a required dependency.
- Guaranteeing live selector stability for every site without an authorized live
  smoke test.
- Transcribing YouTube audio. YouTube remains an optional fast text source only
  when captions or transcripts are already available.

## Confirmed Product Decisions

- Use a dedicated persistent browser profile, not the user's daily Chrome profile.
- Store a remembered per-site grant until the user revokes it.
- Ask in context after a barrier is detected; do not request broad browser access
  at startup.
- Use one visible Playwright window for consent and login. The consent page is a
  static local document rendered with `page.set_content`; no consent web server,
  native dialog toolkit, or browser extension is required.
- During login, the user controls the browser and automation does not fill forms,
  capture screenshots, save traces/HAR, or extract the page.
- After login, allow same-site read navigation under a deterministic mutation
  guard and a bounded recipe.
- Prefer a prebuilt site recipe for known complex sites. Use the generic DOM
  recipe only for unknown or structurally simple sites.
- Reuse the current research depth and evidence pipeline instead of creating a
  separate scraping product.

## Alternatives and Evidence

### Selected: embedded Playwright with a separate profile

Playwright directly supports persistent contexts backed by a user-data directory.
Its current documentation explicitly warns that automating the default Chrome
profile is unsupported and recommends a separate automation directory. This
matches the required privacy boundary and avoids an extra daemon or extension.

### Rejected as the default: attach to daily Chrome through CDP

This path minimizes the first login but exposes a much broader browsing session.
Chrome 136 no longer honors remote-debugging switches for the default data
directory, and Playwright documents CDP connections as lower fidelity than its
native protocol. It is neither the simplest supported product path nor the safest
default.

### Rejected as the core: Browser Use or OpenCLI

OpenCLI can accelerate a prototype and already has several adapters, but it adds a
desktop runtime, browser extension, and local daemon with broad browser
capabilities. Browser Use adds a larger agent runtime, currently requires Python
3.11 while this project supports 3.10, and its cloud profile path introduces a
separate cookie-upload trust decision. Both may remain optional bridge backends.

### User-acceptance evidence

Official platform guidance consistently recommends asking for access in context,
explaining why it is needed, requesting the least power necessary, allowing
denial, and supporting revocation. The selected design follows that pattern. This
is a product inference from permission-design guidance, not a completed user
study, so confidence in acceptance is medium. Engineering and browser-isolation
confidence is high.

Primary references:

- [Playwright BrowserType](https://playwright.dev/python/docs/api/class-browsertype)
- [Playwright authentication](https://playwright.dev/python/docs/auth)
- [Chrome remote debugging changes](https://developer.chrome.com/blog/remote-debugging-port)
- [Chrome extension permission guidance](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions)
- [Android runtime permission guidance](https://developer.android.com/training/permissions/requesting)
- [RFC 8252 browser authorization pattern](https://www.rfc-editor.org/info/rfc8252/)
- [Browser Use](https://github.com/browser-use/browser-use)
- [OpenCLI](https://github.com/jackwener/opencli)

The Research Engine deep run used to start this comparison collected zero rows
because AnySearch returned HTTP 402. Its loop correctly stopped with
`sources_returned_no_evidence`; the design judgment above therefore relies on the
targeted primary references, not on that failed run.

## Loop Contract

```text
Goal:
Collect authorized visible text from a login-gated site and resume the original
research run without account mutation or secret leakage.

Input scope:
The original CollectionRequest, platform plan, exact origin, current depth budget,
an approved recipe, a user consent decision, and a local site-specific profile.

Execute:
1. Attempt public collection and classify the response.
2. Convert a recoverable barrier into AuthChallenge data.
3. Resolve remembered consent or display the consent document.
4. Let the user log in in the visible browser.
5. Switch to capture mode and execute the bounded recipe.
6. Normalize rows and merge them into the original run.
7. Run existing content, quality, relevance, conflict, and claim checks.

Checks:
- consent scope and recipe version are valid;
- login wall is gone;
- every action and request passes CapturePolicy;
- budgets are not exceeded;
- normalized rows contain no sensitive fields;
- invalid/login UI content remains claim-ineligible.

Feedback rules:
- denied -> skip the site and continue other sources;
- auth expired -> allow one user reauthentication;
- policy/robots/paywall denial -> stop the site without browser fallback;
- mutation attempted -> block and abort the site;
- recipe drift -> use generic extraction only if content validity passes;
- rate limit -> stop without same-run retry;
- no GUI/browser -> record human action required and continue public sources.

Records:
auth_challenges.jsonl, query_plan.json, collection_execution.json,
evidence.jsonl, evidence_quality.json, loop_record.json.

Stop conditions:
success when bounded eligible rows are merged and checks pass; otherwise stop for
denial, unavailable browser, login timeout, policy denial, rate limit, mutation,
recipe drift, exhausted budget, or sensitive-data detection.

Human gates:
site consent, login, SSO, MFA, CAPTCHA, entitlement judgment, and the first live
smoke for each authenticated site.

Acceptance:
The run resumes with traceable evidence, no mutation occurs, no secret enters
artifacts, and the stop reason is deterministic.
```

## Architecture

The collection loop gains a second, serialized phase:

```text
public planning and collection
  -> content validity classification
  -> recoverable AuthChallenge(s)
  -> consent resolution
  -> visible user login
  -> authenticated read-only recipe crawl
  -> normalized CollectionResult
  -> existing evidence/quality/claim pipeline
```

Public collection remains concurrent. Authenticated browser collection is serial
because it shares user attention and persistent profile state; this avoids
multiple consent windows, concurrent logins, and profile-lock corruption.

### Components

#### `AuthChallenge`

A serializable record containing:

- stable challenge ID;
- exact origin and platform;
- barrier reason;
- source, query, facet, and pass IDs;
- requested read capabilities;
- recipe ID and version;
- created/resolved timestamps;
- `pending`, `granted`, `denied`, `expired`, or `failed` status;
- deterministic stop reason.

It contains no URL credentials, cookies, headers, page bodies, or browser paths.

#### `ConsentStore`

Stores grants by exact origin plus recipe ID/version. A recipe version change that
alters requested capabilities invalidates the prior grant. The store supports
list and revoke operations and writes atomically with owner-only permissions where
the operating system supports them.

Default path:

```text
~/.research-engine/browser-auth/consents.json
```

Tests and callers can override the root. Consent metadata never enters evidence;
only a stable nonsecret consent ID is referenced.

#### `BrowserSession`

Owns a site-specific `launch_persistent_context` directory and a single-instance
lock:

```text
~/.research-engine/browser-auth/profiles/<recipe-id>/
```

The browser profile is not exported as `storage_state`. Playwright warns that
authentication state files can contain cookies and headers capable of account
impersonation. Profiles are never copied into run directories.

#### Consent document

The connector renders a bundled static HTML document with `page.set_content` in
the same visible browser used for login. It displays:

- exact site and reason;
- research task summary;
- fields and actions requested;
- prohibited actions;
- `Deny` and `Allow and remember` buttons;
- how to revoke later.

All inserted text is HTML-escaped. The document loads no remote scripts, styles,
images, or analytics.

#### `CapturePolicy`

Centralizes browser safety:

- allowed origins and authentication-provider redirects;
- allowed navigation and extraction actions;
- mutation-label and endpoint deny rules;
- download and upload denial;
- default rejection of non-GET requests in generic mode;
- recipe-specific read-only POST allowlists;
- request/result/scroll/page/time budgets.

No recipe bypasses the global mutation deny rules.

#### `SiteRecipe`

Each recipe declares a small data-driven contract:

```text
id, version, platforms, allowed_origins
search URL builder
login-wall and authenticated-state markers
result/container selectors
field selectors and mappings
pagination/scroll strategy
safe expand/read interactions
mutation labels and endpoints
verified read-only POST operations
fixture verification status
live verification status
```

Recipe methods may handle extraction where selectors are insufficient, but the
global connector owns browser lifecycle, consent, budgets, policy, normalization,
and artifacts.

#### `AuthenticatedBrowserConnector`

Consumes a `CollectionRequest`, consent services, browser session, policy, and
recipe. It returns the existing `CollectionResult` type so execution, quality,
repair, and synthesis do not need a parallel evidence model.

## Recovery State Machine

```text
planned
  -> public_attempt
  -> usable -------------------------------> normal evidence pipeline
  -> challenge_detected
       -> policy_denied --------------------> stop site
       -> pending_consent
            -> denied ----------------------> skip site
            -> granted
                 -> pending_login
                      -> login_timeout -----> stop site
                      -> authenticated
                           -> collecting
                                -> budget_exhausted -> complete bounded
                                -> rate_limited ----> stop site
                                -> recipe_drift ----> validated generic fallback or stop
                                -> mutation_blocked -> abort site
                                -> complete --------> evidence pipeline
```

Recoverable reasons are `login_wall`, expired session, user-completable SSO/MFA/
CAPTCHA, and a public JavaScript shell where automated access remains permitted.

Nonrecoverable reasons are robots denial, paywall, missing entitlement, explicit
platform automation denial, repeated rate limiting, and account restriction.
These never cause a headed-browser retry.

## Login and Capture Modes

### Login mode

- The user controls the visible browser.
- Form submission and authentication-provider navigation are permitted because
  the user, not automation, initiates them.
- The connector does not fill inputs, click login controls, save screenshots,
  record traces/HAR, or extract the login page.
- Completion is detected by returning to an allowed target origin and satisfying
  recipe authentication markers while login-wall markers are absent.
- Login wait is bounded to five minutes.

### Capture mode

- Only recipe-declared read interactions are available.
- Generic mode allows same-origin GET navigation, scrolling, pagination, and
  visible text extraction.
- Posting, reactions, social actions, applications, payments, uploads, deletion,
  and settings are denied by semantic action checks and network policy.
- Default policy rejects POST, PUT, PATCH, DELETE, and upload bodies.
- A complex-site recipe may allow a specific POST only when the endpoint and
  operation/body fingerprint have been verified as read-only. Unknown GraphQL
  operations remain blocked.
- A blocked mutation aborts the site rather than attempting an alternate click.

## Browser Crawl Budget

The connector derives bounds from the existing request and depth rather than
creating an unlimited crawler:

- `max_results = request.max_results`;
- `max_pages = max(1, request.max_results)`;
- `max_scrolls = max(3, request.max_results)`;
- capture time: quick 60 seconds, deep 180 seconds, audit 300 seconds;
- login wait: 300 seconds;
- reauthentication: at most one attempt per site per run;
- no-new-content detection stops repeated scrolling early.

The execution report records the observed result/page/scroll counts, elapsed
time, budget stop, and recipe version.

## Recipe Registry

Public APIs and public pages remain preferred. Recipes are fallback or
augmentation paths, not a reason to force browser login.

| Recipe | Initial read scope | Preferred path before browser |
| --- | --- | --- |
| LinkedIn | content search, posts, company pages | browser recipe |
| X | search, posts, threads | public/AgentReach |
| Reddit | search, posts, comments | public/AgentReach |
| Blind | search, posts, comments | browser recipe |
| Glassdoor | companies, jobs, review summaries | public pages |
| Indeed | jobs, company review summaries | official/public pages |
| OnePointThreeAcres | forum search, topics, replies | browser recipe |
| Hacker News | search, stories, comments | Algolia/public pages |
| GitHub | repositories, issues, discussions, releases | GitHub API |
| Stack Overflow | search, questions, answers | public pages |

Each recipe ships with offline HTML/JSON fixtures and a contract test. A recipe
records `fixture_verified` and `live_verified` separately. LinkedIn must complete
one user-authorized, low-volume, read-only live smoke before this feature is
declared complete. Other recipes may ship as fixture-verified and remain visibly
marked until an authorized live smoke is available.

The generic fallback supports same-origin article and list pages using semantic
`main`/`article` content, headings, links, tables, time metadata, and repeated
item containers. It never invents site-specific actions at runtime.

## Runner and CLI Integration

### Runner

1. Execute public requests normally.
2. Derive recoverable challenges from invalid rows and platform plans marked
   `requires_login`.
3. Check global policy before any browser fallback.
4. Execute approved browser requests serially.
5. Merge results while preserving source/query/facet/pass metadata.
6. Write challenges and browser execution telemetry before synthesis.

`ResearchEngine.run` accepts `browser_auth="auto"` by default, with these
semantics:

- `auto`: use a remembered grant and valid profile automatically; otherwise show
  consent only when an interactive GUI is available; in noninteractive contexts,
  record human action required instead of hanging;
- `never`: never launch a browser and keep the current public-only behavior.

Both `research` and `research-engine run` default to `auto`. In a noninteractive
or GUI-less environment, `auto` never opens a window or waits; it records human
action required and continues other sources. Callers can choose
`--browser-auth never` for strict public-only execution.

### Auth management

```text
research-engine auth list
research-engine auth revoke <recipe-or-origin>
research-engine auth clear-profile <recipe>
research-engine doctor browser
```

`clear-profile` is destructive but narrowly scoped and requires confirmation in
interactive use. It removes only the resolved site profile directory.

### Optional dependency

Playwright remains optional for public-only users. Add a `browser` project extra
and make doctor distinguish:

- Python package unavailable;
- browser binary unavailable;
- GUI unavailable;
- available.

No Browser Use, OpenCLI, native GUI toolkit, or web framework is required.

## Evidence and Artifact Contract

Authenticated rows use the existing evidence path with these fields:

```text
connector = authenticated_browser
platform, url, final_url, title, text, author, published_at, metrics
captured_at, access_mode = authorized_browser_session
recipe_id, recipe_version, consent_id, auth_challenge_id
source_id, query_id, facet_id, pass_id
content_valid, content_invalid_reasons, claim_eligible
```

Default capture stores visible normalized text and structured public fields only.
It does not store full DOM, login UI, screenshots, video, HAR, request/response
headers, cookies, local storage, IndexedDB, or the profile path.

New per-run artifact:

```text
auth_challenges.jsonl
```

`collection_execution.json` adds statuses:

- `human_action_required`;
- `browser_unavailable`;
- `consent_denied`;
- `login_timeout`;
- `auth_expired`;
- `policy_denied`;
- `rate_limited`;
- `recipe_drift`;
- `mutation_blocked`;
- `sensitive_data_blocked`.

The loop contract and record expose browser human gates and stop reasons. Login
walls and consent pages remain content-invalid and claim-ineligible.

## Error Handling

| Failure | Required behavior |
| --- | --- |
| No Playwright/browser/GUI | Continue public sources; record unavailable or human action required; do not hang. |
| Consent denied | Skip site and continue other sources. |
| Login timeout or expired auth | Permit one user reauthentication, then stop site. |
| Robots/paywall/entitlement denial | Do not launch browser fallback. |
| Rate limit or account restriction | Stop site without same-run retry. |
| Profile lock | Wait only within the source deadline, then report unavailable. |
| Recipe drift | Use generic extraction only after content validity passes; otherwise stop. |
| Mutation guard triggered | Block action and abort site. |
| Sensitive value in row/artifact | Drop row and fail the existing context-hygiene critical check. |

## Testing

### Unit tests

- AuthChallenge serialization and redaction.
- Consent grant, remembered resolution, revoke, recipe-version invalidation,
  atomic write, and owner-only permission behavior.
- Exact-origin matching; no broad suffix consent.
- Consent HTML escaping and absence of remote assets.
- Public-result-to-challenge classification.
- Browser second-phase request construction and query/facet/pass preservation.
- Budget and no-new-content stopping.
- Mutation-label, form, upload, download, and method denial.
- Verified read-only GraphQL POST allowance and unknown operation denial.
- Sensitive-field and sensitive-value quarantine.
- Auth command target resolution and narrow profile deletion.

### Recipe contract tests

Every approved recipe has fixture-backed tests for:

- login-wall detection;
- authenticated-state detection;
- search URL construction;
- item extraction and canonical URL;
- author/time/metric normalization;
- pagination or scroll stopping;
- mutation denial and read-only request allowance;
- recipe-drift reporting.

### Integration tests

A local deterministic site simulates:

- login wall and user consent;
- user-controlled login and redirect;
- expired session and one reauthentication;
- infinite scroll with repeated content;
- read-only POST and mutation POST;
- user denial;
- login timeout;
- recipe drift and valid/invalid generic fallback.

Use an injectable browser driver for most tests so CI does not require a real
account. A separate marked browser smoke runs only when Playwright and a browser
binary are available.

### Live smoke

With explicit user authorization, run a low-volume LinkedIn smoke that:

- opens the consent document;
- lets the user log in;
- collects at most three visible results;
- performs no mutation;
- writes normalized rows and challenge telemetry;
- confirms no sensitive data appears in artifacts;
- revokes consent or preserves it according to the user's selected test path.

No other live account is required to complete the core implementation.

### Regression

- Run the full `pytest` suite.
- Run browser-focused tests with the optional extra.
- Run `research-engine doctor browser`.
- Re-run an adversarial public pack to ensure login walls and block pages remain
  invalid evidence.
- Run one public-only research command with `--browser-auth never` to verify
  unchanged public behavior.

## Acceptance Criteria

1. Login walls, CAPTCHA pages, consent documents, and JS shells cannot become
   claim-eligible evidence.
2. A recoverable barrier produces an auditable challenge with preserved research
   provenance.
3. In interactive mode, user consent and login resume the same run.
4. Remembered site consent and persistent login can be listed, revoked, and
   cleared without exposing secrets.
5. Generic capture is same-origin and bounded; ten approved recipes pass their
   offline contracts.
6. LinkedIn passes one user-authorized read-only live smoke with at most three
   visible results.
7. Mutation attempts are blocked and abort site collection; verified read-only
   POST requests require a recipe allowlist.
8. Public-only and noninteractive runs never hang and continue to degrade
   honestly.
9. Research artifacts contain no cookie, credential, auth header, storage state,
   login DOM, screenshot, HAR, or browser-profile path.
10. Full tests pass and connector, CLI, safety, and doctor documentation reflect
    the shipped behavior.

## Implementation Sequence

The later implementation plan should keep each stage independently testable:

1. challenge, consent, policy, recipe, and artifact data contracts;
2. persistent browser session and static consent document;
3. local simulated login/crawl integration path;
4. runner fallback/resume and CLI/auth management;
5. generic recipe and ten site recipes with offline fixtures;
6. documentation, doctor, security checks, and regressions;
7. user-authorized LinkedIn live smoke and final acceptance review.

## Risks and Mitigations

- **Selector drift:** version recipes, keep fixtures, report drift, and never
  silently return empty success.
- **Read POST misclassification:** default deny; require explicit operation/body
  fingerprints and tests.
- **Profile compromise:** isolate per site, owner-only local paths, no export, no
  Git/artifact inclusion, explicit clear command.
- **User confusion:** request in context, show exact site and scope, use a single
  visible window, and provide revoke commands.
- **Platform policy change:** stop on explicit automation denial, rate limit, or
  account restriction; update recipes only after policy review.
- **Noninteractive deadlock:** detect unavailable interaction before launching and
  emit `human_action_required`.
- **Optional dependency failure:** preserve public-only behavior and expose doctor
  diagnostics.

## Design Review Result

The architecture, recovery state machine, component/recipe contract, and
error/testing/acceptance sections were approved by the user on 2026-07-17. No
implementation starts until the written spec itself is reviewed and approved.
