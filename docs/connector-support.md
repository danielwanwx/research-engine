# Connector Support Matrix

Research Engine keeps collection behind connector contracts so the core runner
stays source-agnostic. Optional upstream tools should degrade gracefully when
they are not installed or not authenticated.

| Connector | Status | Access mode | Primary use | Notes |
| --- | --- | --- | --- | --- |
| `manual` | Built in | Local | Pack-provided or hand-authored evidence rows | Useful for tests and small curated datasets. |
| `external_jsonl` | Built in | Authorized export | Import evidence from logged-in browser tools, paid sources, or proprietary collectors | Does not read cookies or control a browser. |
| `web_page` | Built in | Public web | Fetch explicit seed pages | Static page fetch only; not a crawler. |
| `finance_quote` | Built in | Public endpoint | Quote snapshots for watchlist tickers | Uses a public chart-style endpoint. |
| `github_public_search` | Built in | Public endpoint | Search public GitHub repositories without login | Uses GitHub's unauthenticated search API as a fallback; rate limits apply. |
| `agent_reach_bridge` | Built in, optional upstream tools | Public or authorized CLI | Normalize AgentReach-compatible CLI output | Missing upstream commands warn instead of failing the run. Commands run without a shell and must use allowlisted read-oriented executables such as `twitter`, `rdt`, `xhs`, `xq`, `gh`, and `yt-dlp`. |
| `opencli_bridge` | Built in, optional upstream tool | Authorized read-only adapter | Use OpenCLI adapters and structured exports | Missing OpenCLI warns instead of failing the run. Recipes and commands must not include secrets; only the allowlisted `opencli` entrypoint runs by default. |
| `web_crawler` | Planned | Public or authorized renderer | Sitemap, bounded crawl, optional Playwright rendering | Browser dependencies should be optional extras. |
| `chrome_platform_sampler` | Planned | Local authorized browser | Low-volume read-only X, Reddit, LinkedIn, Xiaohongshu, and YouTube sampling | Must not mutate account state. |

Use `research-engine doctor` to inspect local optional capabilities. The command
writes `state/connector_capabilities.json` by default.

External JSONL paths are recorded as filename plus stable path hash in artifacts,
not as full local paths.
Bridge command output, stderr, command argv, URL parameters, and command-like
payload metrics are sanitized before artifact writes.
