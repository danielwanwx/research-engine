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
| `agent_reach_bridge` | Built in, optional upstream tools | Public or authorized CLI | Normalize AgentReach-compatible CLI output | Missing upstream commands warn instead of failing the run. |
| `opencli_bridge` | Planned | Authorized browser workflow | Use OpenCLI adapters and recorded workflows | Recipes must not include secrets. |
| `web_crawler` | Planned | Public or authorized renderer | Sitemap, bounded crawl, optional Playwright rendering | Browser dependencies should be optional extras. |
| `chrome_platform_sampler` | Planned | Local authorized browser | Low-volume read-only X, Reddit, LinkedIn, Xiaohongshu, and YouTube sampling | Must not mutate account state. |

Use `research-engine doctor` to inspect local optional capabilities. The command
writes `state/connector_capabilities.json` by default.
