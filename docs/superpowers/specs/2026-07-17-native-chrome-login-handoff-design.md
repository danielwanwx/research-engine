# Native Chrome Login Handoff Design

**Date:** 2026-07-17

**Status:** Approved; amended after macOS live smoke

**Parent design:**
`docs/superpowers/specs/2026-07-17-generic-authenticated-browser-crawler-design.md`

## Problem

The first LinkedIn live smoke reached the consented Playwright browser, but
Google rejected LinkedIn's Google OAuth popup with “This browser or app may not
be secure.” This is expected policy behavior: Google does not permit sign-in
inside browsing environments that provide automation features.

Changing user agents, hiding automation flags, or adding stealth tooling would
be brittle and would conflict with the project's no-bypass rule. The login
stage must therefore run in a normal browser that Research Engine does not
control.

## Decision

Keep the dedicated per-site profile and Playwright capture phase, but split the
workflow at login:

1. Playwright displays the existing exact-origin consent document.
2. After consent, Playwright navigates to the target only to determine whether
   authentication is required.
3. If login is required, Research Engine closes the Playwright context so the
   profile is unlocked.
4. Research Engine launches a normal installed Chrome process with that same
   dedicated `--user-data-dir` and the target URL. It does not enable remote
   debugging, CDP, injected extensions, scripts, or automation.
5. The user completes login, SSO, MFA, or CAPTCHA, returns to a loopback-only
   Research Engine tab, and clicks **I’m signed in — continue**.
6. Research Engine reopens the same profile through Playwright, verifies that
   login markers are gone or authenticated markers are present, installs the
   read-only request guard, and performs bounded extraction.

The existing remembered-consent, profile isolation, capture budgets, recipe
registry, artifacts, and noninteractive behavior remain unchanged.

## Why This Approach

### Selected: normal Chrome handoff

- Supports Google OAuth in a full browser without automating authentication.
- Preserves a dedicated site profile instead of accessing the user's personal
  Chrome profile.
- Adds one explicit user action: confirm completion in the dedicated browser.
- Reuses the existing Playwright extraction and safety policy.

### Rejected: require LinkedIn email/password

This is a smaller code change but excludes users who rely on Google/enterprise
SSO and creates pressure to automate or collect credentials.

### Rejected: attach to the user's existing Chrome profile

This reduces login friction but unnecessarily expands access to unrelated
cookies, extensions, accounts, and browsing state. Chrome also does not support
automating its default profile as a stable product contract.

## Components

### Login browser resolution

The connector resolves a stable, full Chrome executable using a narrow order:

1. an explicit `RESEARCH_ENGINE_LOGIN_BROWSER` executable path;
2. standard Google Chrome locations for macOS, Windows, and Linux;
3. `google-chrome`, `google-chrome-stable`, `chromium`, or `chromium-browser`
   on `PATH`.

Chrome for Testing and Playwright-managed Chromium are not eligible login
browsers. Doctor reports the resolved login browser separately from the
Playwright capture browser.

### Native login handoff

One small helper receives the executable, profile directory, target URL, and
timeout. It launches an argv list with `subprocess.Popen` and no shell. The
minimum arguments are:

- `--user-data-dir=<dedicated profile>`;
- `--no-first-run`;
- `--disable-background-mode`;
- a nonce-protected Research Engine confirmation page bound to loopback only;
- the exact target URL.

The helper waits for either a normal browser exit or explicit completion on the
local confirmation page. On confirmation it stops only the dedicated process it
created, then checks the profile lock before Playwright reopens it. Research
Engine does not inspect site pages, keystrokes, network traffic, cookies, or
storage. The loopback server logs nothing and shuts down after the handoff.

### Playwright resume

The current browser flow becomes two bounded Playwright contexts around an
optional native-login phase. Consent is shown only in the first context. The
second context navigates back to the original target, verifies authentication,
then runs the existing request guard and extractor.

An injected login-handoff callable keeps tests deterministic and avoids opening
real GUI applications in the test suite.

## State and Security

- The normal browser uses only the dedicated recipe/origin profile.
- Personal/default Chrome profiles are never opened or copied.
- Research Engine code never reads, copies, logs, or exposes credentials,
  cookies, or OAuth tokens from the browser profile.
- Login is never automated, recorded, screenshotted, traced, proxied, or
  inspected.
- No stealth flags, user-agent spoofing, CAPTCHA bypass, proxy rotation, or
  fingerprint evasion is introduced.
- Consent remains exact-origin and recipe-versioned.
- Login completion requires an unguessable in-memory loopback URL and an
  explicit POST; no callback value is written to artifacts.
- The mutation guard is installed before automated capture resumes.
- Profile paths and browser command lines do not enter run artifacts.

## Statuses and Failure Handling

The browser challenge records one of these sanitized terminal states:

- `login_browser_unavailable`: no supported normal browser executable;
- `login_browser_timeout`: the user did not confirm completion or exit the
  browser within the five-minute login budget;
- `login_cancelled`: the user cancelled on the confirmation page;
- `login_browser_failed`: the normal browser could not start or exited
  abnormally;
- `profile_lock_timeout`: the login browser exited but did not release the
  dedicated profile promptly;
- `login_incomplete`: Playwright resumed but the site still showed a login
  marker;
- `completed`: authentication was verified and bounded extraction completed
  (`ready` remains the connector's internal success status).

All non-ready states produce zero authenticated evidence rows and retain an
explicit human/setup action. There is no fallback to stealth or a personal
profile.

## CLI and User Experience

The existing command remains unchanged:

```bash
research-engine run "LinkedIn agent engineering evidence" --browser-auth auto
```

The consent page explains the handoff before the user allows it. When normal
Chrome opens, it contains the target and a local Research Engine tab. After
login, the user returns to that tab and clicks **I’m signed in — continue**. This
explicit signal works even when macOS keeps Chrome alive after its last window
closes; no cookie is copied.

`research-engine doctor browser` adds the normal login-browser check and gives
the remediation when only Playwright Chromium is available.

## Testing

Deterministic tests cover:

- executable resolution and explicit override validation;
- argv construction without a shell, remote debugging, or automation flags;
- Playwright context closes before native Chrome starts;
- successful handoff resumes capture with the same profile;
- browser unavailable, cancellation, timeout, nonzero exit, profile-lock
  timeout, and login incomplete statuses;
- denied consent and noninteractive runs never launch Chrome;
- command lines, profile paths, cookies, and credentials stay out of artifacts.

After focused and full tests pass, one user-operated LinkedIn smoke verifies:

1. Google OAuth opens in normal Chrome;
2. the user explicitly confirms completion after login;
3. Playwright resumes and collects at most three visible rows;
4. `auth_challenges.jsonl` records `completed`;
5. the run bundle contains no sensitive browser state.

## Non-Goals

- Automating credentials, SSO, MFA, or CAPTCHA.
- Supporting Safari or Firefox in the first handoff implementation.
- Reusing the user's default Chrome profile.
- Keeping native Chrome open while Playwright simultaneously attaches.
- Circumventing provider automation detection.
