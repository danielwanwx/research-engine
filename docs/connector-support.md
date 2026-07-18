# Connector Support Matrix

Research Engine keeps collection behind connector contracts so the core runner
stays source-agnostic. Optional upstream tools should degrade gracefully when
they are not installed or not authenticated.

| Connector | Status | Access mode | Primary use | Notes |
| --- | --- | --- | --- | --- |
| `manual` | Built in | Local | Pack-provided or hand-authored evidence rows | Useful for tests and small curated datasets. |
| `external_jsonl` | Built in | Authorized export | Import evidence from logged-in browser tools, paid sources, or proprietary collectors | Does not read cookies or control a browser. |
| `web_search` | Built in | Anonymous AnySearch or explicit SearXNG | Bounded unseeded discovery | Query text crosses the selected third-party boundary. Rows are `discovery_only`; snippets can never support claims. |
| `web_page` | Built in | Public web | Canonical refetch and explicit seed pages | SSRF redirects and robots decisions are checked; honest UA, per-host limits, semantic HTML/JSON extraction, and optional local PDF extraction are recorded. |
| `finance_quote` | Built in | Public endpoint | Quote snapshots for watchlist tickers | Uses a public chart-style endpoint. |
| `github_public_search` | Built in | Public endpoint; optional environment token | Search and rank public GitHub repositories | Best-match retrieval retains raw and engine rank, license, archived, maintenance, adoption, topics, and default branch. `GITHUB_TOKEN`/`GH_TOKEN` is optional and never written to artifacts. |
| `official_job_discovery` | Built in | Public official ATS/company sites | Scoped point-in-time job snapshots | Requires explicit company, role, level, and geography scope for quantitative output. Only active final official pages count. |
| `agent_reach_bridge` | Built in, optional upstream tools | Public or authorized CLI | Normalize AgentReach-compatible CLI output | Missing upstream commands warn instead of failing the run. Commands run without a shell and must use allowlisted read-oriented executables such as `twitter`, `rdt`, `xhs`, `xq`, `gh`, and `yt-dlp`. |
| `opencli_bridge` | Built in, optional upstream tool | Authorized read-only adapter | Use OpenCLI adapters and structured exports | Missing OpenCLI warns instead of failing the run. Recipes and commands must not include secrets; only the allowlisted `opencli` entrypoint runs by default. |
| `authenticated_browser` | Built in, optional Playwright plus normal Chrome | User-consented dedicated browser profile | Recover supported login/JavaScript barriers, then normalize visible text | Public collection runs first. Exact-origin consent is remembered per recipe version. Normal Chrome handles user-controlled login; Playwright resumes only for guarded capture. |
| `web_crawler` | Planned | Public or authorized renderer | Sitemap and bounded crawl | Playwright remains an optional rendered-page fallback, not a crawler dependency. |

Use `research-engine doctor` to inspect local optional capabilities. The command
writes `state/connector_capabilities.json` by default.

The first authenticated-browser recipes are LinkedIn, X, Reddit, Blind,
Glassdoor, Indeed, 一亩三分地, Hacker News, GitHub, and Stack Overflow. They are
fixture-verified; live platform verification is tracked separately because site
markup can change. YouTube remains a fast transcript/caption source through
`yt-dlp` and is not part of this authenticated page recipe batch.
Other recoverable login/JavaScript barriers use a conservative generic recipe
with an origin-isolated profile and article/main-text selectors. A generic
recipe is never labeled fixture- or live-verified.

Install and inspect the optional browser runtime with:

```bash
python -m pip install -e '.[browser]'
playwright install chromium
research-engine doctor browser
```

Login and capture are deliberately separate. When a site needs authentication,
Research Engine closes Playwright and opens ordinary installed Chrome with the
same dedicated site profile. Complete SSO/MFA/CAPTCHA, return to the local
Research Engine tab, and explicitly click **Close window and verify sign-in**. Playwright
then reopens the profile for bounded read-only extraction. The confirmation button
now closes Chrome briefly for verification; if sign-in is still incomplete, Chrome
reopens automatically for up to three attempts within one five-minute budget.
Google OAuth is never attempted in Chrome for Testing. If Chrome is installed in a
nonstandard location,
set `RESEARCH_ENGINE_LOGIN_BROWSER` to its executable.

`--browser-auth auto` is the default. It opens a visible site-specific profile
for a supported recoverable barrier, a platform named in the topic, or a platform
scheduled by the selected pack and depth. Deep and audit `job_market` runs schedule
LinkedIn as advisory discovery coverage; official careers/ATS pages remain
authoritative for active openings. A missing advisory source is recorded as a
coverage warning instead of blocking public-source completion. A platform named
explicitly in the topic remains a blocking human gate.
`--browser-auth never` enforces public-only collection. Noninteractive runs do
not wait: they write `auth_challenges.jsonl` with `human_action_required`.

Remembered grants and profiles are managed narrowly:

```bash
research-engine auth list
research-engine auth revoke linkedin
research-engine auth clear-profile linkedin
```

External JSONL paths are recorded as filename plus stable path hash in artifacts,
not as full local paths.
Bridge command output, stderr, command argv, URL parameters, and command-like
payload metrics are sanitized before artifact writes.

Use `--search-provider none` to prevent third-party query submission. A SearXNG
provider is used only when its endpoint is explicitly supplied. Robots denial,
rate limits, retry exhaustion, deadlines, and canonical-refetch failure remain
observable as separate statuses; they never relax claim eligibility.

The browser connector never automates credentials or CAPTCHA, exports browser
storage, or writes screenshots, traces, HAR, cookies, or headers to run
artifacts. It does not bypass robots denial, paywalls, rate limits, or account
entitlements.

Handoff failures are recorded as `login_browser_unavailable`,
`login_browser_timeout`, `login_browser_failed`, `profile_lock_timeout`, or
`login_incomplete`; user cancellation is `login_cancelled`. None of them fall
back to a personal profile or stealth.
