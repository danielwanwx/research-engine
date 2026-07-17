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
| `web_crawler` | Planned | Public or authorized renderer | Sitemap and bounded crawl | Playwright remains an optional rendered-page fallback, not a crawler dependency. |
| `chrome_platform_sampler` | Planned | Local authorized browser | Low-volume read-only X, Reddit, LinkedIn, Xiaohongshu, and YouTube sampling | Must not mutate account state. |

Use `research-engine doctor` to inspect local optional capabilities. The command
writes `state/connector_capabilities.json` by default.

External JSONL paths are recorded as filename plus stable path hash in artifacts,
not as full local paths.
Bridge command output, stderr, command argv, URL parameters, and command-like
payload metrics are sanitized before artifact writes.

Use `--search-provider none` to prevent third-party query submission. A SearXNG
provider is used only when its endpoint is explicitly supplied. Robots denial,
rate limits, retry exhaustion, deadlines, and canonical-refetch failure remain
observable as separate statuses; they never relax claim eligibility.
