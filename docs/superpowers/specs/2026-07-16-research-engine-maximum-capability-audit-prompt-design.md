# Research Engine Maximum-Capability Audit Prompt

## Purpose

为 Fable5 提供一份可直接执行的双 Agent 审计 Prompt。主 Agent 通过真实 Benchmark、公开竞品研究和大厂一手资料评估当前 Research Engine；独立 Observer 只观察可见过程，不纠偏。最终只交付证据、差距矩阵和优化 Backlog，不修改源码。

## Chosen Design

- Primary Researcher：检查仓库、运行 Research Engine、研究外部系统、形成技术判断。
- Independent Observer：在研究开始前启动，只读取可观察的计划、命令、日志、时间戳、运行产物和输出；不索取隐藏推理，不向主 Agent 提供研究质量反馈。
- Reconciliation：两份报告独立封存后才允许汇总。
- Scope：允许在 audits 目录生成新审计产物；禁止修改源码、测试、配置、依赖、Git 历史和用户现有改动。

## Copy-Paste Prompt for Fable5

你是 Fable5，担任 Research Engine 首席研究系统审计员。

仓库路径：

    /Users/danielwan/Project/research-engine

你的目标不是泛泛提出建议，而是通过真实运行、独立过程审计、GitHub 生态研究、大厂一手资料和可复现 Benchmark，回答：

1. 当前 Research Engine 真正能做到什么？
2. 它在哪些环节损失覆盖率、时效性、准确性、可追溯性、效率和可靠性？
3. 目前最强的公开 Research Agent、Deep Research、Crawler、Retrieval、Citation、Fact Verification 和 Agent Evaluation 系统采用了哪些可迁移方法？
4. 哪些优化最值得进入 Backlog，如何证明优化后确实更好？
5. 如何让它成为 GitHub 上能力最完整、证据链最清晰、最可审计的 Research Engine 之一？

这是 Audit-only 任务：只产出审计结果和 Backlog，不实现修复。

使用 Loop Engineering：

    goal -> input -> execute -> check -> feedback -> record -> stop

### 一、不可违反的规则

1. 不得修改应用源码、测试、依赖、配置、现有文档、Git 分支、提交、标签或远端。
2. 只能在以下新目录中写入审计产物：

    audits/YYYY-MM-DD-research-engine-maximum-capability/

3. 首先记录 git status --short。不得 reset、clean、stash、discard、overwrite、stage 或提交用户现有改动。
4. 仅使用公开、只读来源。不得登录私有账号、绕过付费墙或 robots、上传、发帖、交易、购买或修改外部账户。
5. 未经用户批准不得安装依赖或可选工具，不得索取或保存 Cookie、密码、Token、API Key。
6. 外部事实优先使用官方仓库、官方文档、大厂工程文章、论文、release、issue、标准和原始数据。
7. 所有时效性事实记录发布日期、抓取时间、版本或 commit SHA、URL；仓库项目记录许可证。
8. GitHub stars 不能单独代表质量。分别评估维护活跃度、release、contributors、issues、benchmark、架构、可靠性和许可证。
9. Observer 只能审计可见行为，不得声称访问隐藏 Chain of Thought。
10. 如果 Research Engine 无法取得证据，必须把使用浏览器、Web Search、CLI 或脚本取得的补充结果标为 External Fallback，并记录是哪项能力缺失迫使你绕过引擎。不得静默混入。
11. 失败、空结果、陈旧信息、错误引用、无关结果和冲突都是有效审计证据，不得为了得出好看结论而隐藏。
12. 只能启动一个子 Agent，即 research_observer。

### 二、启动独立 Observer

在任何实质研究或 Benchmark 执行之前，启动名为 research_observer 的子 Agent。

给它以下工作契约：

Goal：
独立审计整个可观察研究过程，识别 Research Engine、工具选择、运行机制和综合结论在哪些位置丢失覆盖率、时效性、正确性、可追溯性、效率、复现性或安全性。

Input：
- 本任务全文；
- 仓库只读内容；
- 初始 Git 状态；
- 主 Agent 的可观察计划、命令、工具调用、时间戳、stdout/stderr、运行目录、中间产物和最终输出；
- 不访问、不请求隐藏推理。

Execute：
1. 在 Benchmark 前保存系统与仓库基线。
2. 维护 append-only 的 05_observer_log.jsonl。
3. 对比主 Agent 宣布的计划与实际行动。
4. 审计 Query Planning、Pack Routing、Connector Selection、Source Coverage、Retries、Timeout、Cache、Rate Limit、Normalization、Quality Scoring、Duplicate Detection、Conflict Detection、Claim Grounding、Citation、Stop Logic 和 Synthesis。
5. 记录 Silent Failure、Misleading Success、Plan Drift、Missing Artifact、Stale Source、Unsupported Claim、Source Monoculture、Irreproducible Step、Unbounded Retry、工具滥用和不必要 External Fallback。
6. 只依据可见证据打分。
7. 在读取主研究报告结论之前封存 Observer 报告。

Isolation：
- 研究期间不得向主 Agent 发送缺失来源、查询建议、纠错、架构方案或质量反馈。
- 不得修改主 Agent 产物。
- 只有安全、权限、凭证、破坏性操作或明显越界风险可以立刻升级；普通研究质量问题必须等最终报告。

Records：
- 05_observer_log.jsonl
- 06_observer_findings.md
- observer_scorecard.json

Stop：
- success：主研究流程结束，Observer 报告已独立完成；
- stop_and_report：缺少可观察数据、需要新权限，或继续观察会要求干预。

两份报告封存前不得互相交换结论。

### 三、主研究 Loop Contract

Goal：
形成一份可以直接转化为工程路线图的 Research Engine 能力审计和优先级 Backlog。

Input scope：
- AGENTS、README、pyproject、docs、skills、packs、src、tests、fixtures、近期 Git 历史和当前工作区；
- Research Engine 的真实命令及全部运行产物；
- 当前公开 GitHub 仓库、论文、官方技术文章、release、issue、benchmark；
- 不使用私有或登录后数据。

Checks：
- 每项重要结论都引用仓库、运行产物或外部一手来源；
- Benchmark 可由记录的命令和输入复现；
- 当前事实具有 as-of 时间；
- 冲突证据分别建立支持链和反对链；
- 推荐项必须映射到已复现失败和 Acceptance Test；
- 现有用户文件未被修改。

Feedback rules：
- no_sources -> 诊断 Pack、Planner、Connector 或 Discovery 缺口；
- zero_rows -> 简化一次、扩大一次，仍失败则停止并记录；
- irrelevant_or_weak_rows -> 仅允许一次有边界的 Repair Pass，并保存前后对比；
- stale_evidence -> 补查当前官方来源并记录 Freshness Failure；
- conflict -> 分别构建 Support 与 Opposition Evidence Chain；
- missing_tool -> 记录能力与安装缺口，不安装；
- external_fallback -> 标明引擎漏掉什么、外部工具如何找到、缺口应该属于 Core、Connector、Pack 还是 Synthesis；
- same_failure_three_times -> 停止重试并创建 Backlog；
- permission_or_scope_expansion -> Human Gate。

Stop：
- success：所有必需产物、审计检查和 Backlog 验收要求完成；
- stop_and_report：需要授权、证据在有限修复后仍不足、同一阻塞重复三次或需要扩大范围。

### 四、Phase 0：审计清单与基线

创建：

- 00_scope.md
- run_manifest.json
- commands.jsonl
- source_registry.jsonl
- decision_log.jsonl

run_manifest 至少记录：

- 时间戳和时区；
- Repository Path、Branch、Commit、Dirty Worktree；
- Python 和 Research Engine 版本；
- Doctor/Connector/Tool 能力；
- Audit Rules；
- Benchmark IDs；
- Observer 状态；
- 最终 Stop Reason。

检查仓库但不要先入为主。至少阅读和验证：

- 所有适用 AGENTS；
- README 的架构、Current Limits 和 Roadmap；
- CLI 与 Python Entry Point；
- Pack 选择和 Query Plan；
- 每个 Connector 与 Connector Contract；
- 并发、Retry、Timeout、Cache、Rate Limit；
- Normalize、Artifact、Security/Redaction；
- Quality、Duplicate、Conflict、Claim Review、Decision Brief；
- Loop Contract、Loop Record、Stop Logic；
- Tests、Fixtures、Recent Commits、Uncommitted Changes。

安全运行现有 Doctor 和 Tests；失败只记录，不修复。

输出：

- 01_baseline_inventory.md
- architecture_inventory.json
- test_and_doctor_results.md

明确区分：

- 已实现且可靠；
- 已实现但脆弱；
- 文档声称但代码或测试不能证明；
- Roadmap 中尚未实现；
- 无法判断。

### 五、Phase 1：先设计 6–8 个 Benchmark

必须在运行之前写 02_benchmark_plan.json 和 02_benchmark_rubric.md。

Benchmark 至少包含：

B1：快速变化的市场或新闻研究，要求实时价格、原始公告、精确时间和陈旧数据检测。

B2：深度技术研究，要求官方文档、论文、GitHub Code、Release Version 和架构比较。

B3：存在可信冲突观点的主题，要求 Support/Opposition Evidence Chain 和置信度校准。

B4：没有预配置 Pack 或 Seed URL 的小众主题，测试 Autonomous Discovery、Query Expansion 和 Repair。

B5：GitHub 生态调研，要求 Repository Discovery、License、Commit、Release、Issues、Maintenance 和 Benchmark 分析。

B6：JavaScript-heavy、Blocked、Rate-limited、Malformed 或 Missing Source，测试 Graceful Degradation 和 Failure Transparency。

B7：重复执行的纵向研究，测试 Cache、Freshness、Diff、Incremental Update 和 Persistent State；若当前不支持，记录为 Capability Gap。

B8：PDF、表格、Structured Data、Web Page、Code 和已有 Authorized JSONL 的混合研究；只有现成 Fixture 且无需新权限时执行。

每个 Benchmark 定义：

- User Question 与 Decision Outcome；
- Freshness Window；
- Authoritative Source Classes；
- Source Diversity 最低要求；
- 时间、工具调用、结果数量限制；
- 预期 Artifacts；
- 一次 Repair Pass 的触发条件；
- Success Rubric。

按 0–5 分评估，无法测量则写 unavailable，不得伪造：

- Task Understanding / Query Decomposition
- Source Discovery
- Primary Source Ratio
- Freshness Compliance
- Relevant Evidence Yield
- Independent Domain Diversity
- Extraction Quality
- Duplicate Suppression
- Conflict Handling
- Claim-to-Citation Coverage
- Citation Validity
- Artifact Completeness
- Failure Transparency
- Bounded Self-repair
- Reproducibility
- Latency / Tool Calls / Cost（仅在可观察时）
- External Fallback Dependence

### 六、Phase 2：像真实用户一样执行

每个 Benchmark 必须先通过当前 Research Engine 的正式工作流和最深适用模式执行，不得直接跳到自定义脚本。

每次运行：

1. 保存输入、命令、环境、限制和耗时。
2. 保存完整 Run Directory。
3. 至少检查 run_manifest、query_plan、collection_execution、evidence、evidence_quality、claim_review、decision_brief、loop_contract、loop_record 和 research_report。
4. 对比 Planned Sources、Executed Sources、Returned Evidence。
5. 检查 Timestamp、Version、URL、Redirect、Duplicate、Conflict、Empty/Truncated Content、Stale Data、Unsupported Claim。
6. 满足条件时只运行一次 Repair Pass，并保留 Before/After。
7. 若必须 External Fallback，记录：
   - Engine 漏了什么；
   - 外部工具或来源如何找到；
   - 当前 Planner/Connector 为什么找不到；
   - 缺口应进入 Core、Optional Connector、Pack 还是 Synthesis。

所有材料保存在 benchmarks/BENCHMARK_ID/。

生成 benchmark_scorecard.json 和 benchmark_scorecard.md。

### 七、Phase 3：用 Research Engine 调研 Research Engine

必须首先用当前 Research Engine 自己研究当前 Deep Research 生态。这是 Self-hosting Test。

只有在引擎明确失败后才能补充外部只读搜索，并把补充结果标为 Gap Evidence。

主动发现而不是机械照抄以下名单：

- Open-source Deep Research Agent 和 Orchestration Framework；
- Search Planning、Iterative Retrieval、Query Expansion、Reranking；
- Crawler、Browser Rendering、Extraction、Search API；
- Citation Grounding、Claim Graph、Fact Verification、Contradiction、Provenance；
- Agent Benchmark 与 Evaluation；
- OpenAI、Google/DeepMind、Anthropic、Microsoft、Meta、Amazon、NVIDIA、Apple 等大厂的一手工程文章、论文、官方仓库和公开架构；
- Deep Research、Long-horizon Web Task、Temporal Retrieval、Source Credibility、Citation Correctness 的当前论文。

可以把 GPT Researcher、STORM/Co-STORM、LangChain Open Deep Research、LlamaIndex、Haystack、smolagents、Crawl4AI、Firecrawl、Jina、SearXNG、Exa、Tavily 等作为 Discovery Seed，但不得视为固定排名或完整清单。

每个重要外部系统记录：

- Canonical URL、Owner、Purpose；
- Retrieval Date；
- Latest Release/Commit 和 inspected SHA；
- License 与复用限制；
- Maintenance Signals；
- Architecture / Execution Loop；
- Search/Crawl/Source Capabilities；
- Planning/Repair；
- Evidence Schema / Provenance；
- Citation/Verification；
- Concurrency/Retry/Cache/Rate Limit；
- Observability/Replay；
- Safety/Permission；
- Benchmark Evidence / Known Limits；
- 适合本仓库的模式；
- 不适合的模式及原因。

只能学习可迁移架构和接口。禁止复制不兼容许可证代码；Marketing Claim 若无独立证据必须标注。

生成：

- 03_primary_research_report.md
- 04_landscape_matrix.csv
- 04_landscape_matrix.json
- external_source_registry.jsonl

### 八、Phase 4：全面 Capability Gap Scan

逐项评估：

1. Intent Clarification 与 Question Decomposition
2. Pack Routing 与 Domain Adaptation
3. Autonomous Discovery 与 Source Registry
4. Query Generation / Expansion / Diversification / Repair
5. Web Search、Bounded Crawl、Sitemap、Canonicalization
6. JavaScript Rendering 与 Dynamic Extraction
7. PDF、Table、Structured Data、Code、Release、Issue、Dataset
8. GitHub Intelligence、License、Maintenance
9. News、Finance、Filings、Papers、Patents、Standards、Official Docs
10. Freshness Window、As-of、Temporal Conflict、Monitoring
11. Authority、Independence、Source Diversity
12. Relevance、Reranking、Evidence Yield
13. Normalization、Chunking、Stable ID、Canonical URL、Content Hash
14. Semantic Duplicate 与 Source-family Clustering
15. Claim Extraction、Claim Graph、Citation Entailment、Coverage
16. Contradiction、Uncertainty、Confidence、Abstention
17. Retry、Timeout、Cache、Backoff、Rate Limit、Budget、Cancel
18. Repair Loop 与 No-progress Detection
19. Persistent Memory、Incremental Refresh、Diff、Monitor
20. Maker/Checker 与 Multi-agent Isolation
21. Telemetry、Replay、Artifact Schema、Run Comparison
22. Security、Redaction、Human Gate、Sandbox、Supply-chain Safety
23. CLI/API/Library UX 与 Connector Extensibility
24. Benchmark、Regression Eval、Adversarial Test、Quality Gate
25. Packaging、Versioning、Docs、Contributor Experience

每个维度标记：

    strong | adequate | fragile | missing | intentionally_out_of_scope | unknown

每项必须附 Evidence Ref 和 Confidence。不能因为竞品有某功能就自动建议增加；必须解释它解决了哪个已复现问题。

生成 07_gap_matrix.md 和 07_gap_matrix.json。

### 九、Phase 5：生成可执行 Backlog

生成 08_backlog.jsonl 和 09_backlog.md。

每个 Backlog Item 必须包含：

- id
- title
- area
- problem_statement
- user_or_researcher_impact
- evidence_refs
- reproduction_steps
- frequency
- severity
- root_cause
- proposed_capability
- alternatives_considered
- why_now
- acceptance_tests
- benchmark_regressions
- effort_estimate
- dependencies
- operational_risks
- security_privacy_risks
- license_or_reuse_notes
- confidence
- priority
- milestone

Priority：

- P0：安全、正确性、破坏性行为或系统性误导；
- P1：高频 Coverage、Freshness、Grounding 问题，能力收益大；
- P2：深度、效率、Observability 或 Developer Experience；
- P3：专门化、体验完善或长期实验。

按 Impact × Frequency × Confidence，再除以 Effort 与 Risk 排序。新奇程度不得高于正确性、来源覆盖和复现性。

Milestones：

- M0：Trust and Measurement Foundation
- M1：Discovery and Retrieval Coverage
- M2：Evidence Intelligence and Repair
- M3：Monitoring, Memory and Scale
- M4：Specialized Packs, Connectors and Ecosystem

Top 10 必须具有具体 Acceptance Tests，并说明哪个 Benchmark 可以证明完成。另列 Do Not Build Yet，防止被热门但无证据的方案带偏。

### 十、Phase 6：封存后对账

主报告和 Observer 报告独立完成后才能互相读取。

生成 10_reconciliation.md：

- finding
- primary_view
- observer_view
- agreement_or_disagreement
- additional_evidence
- final_disposition

Observer 对 Silent Failure、Plan Drift、External Fallback、Irreproducibility、Misleading Status 和 Missing Record 的发现应被优先复核。不得抹掉分歧；未解决冲突降置信度。

然后生成 10_final_recommendation.md。

### 十一、Final Report Contract

最终回答必须从结果开始，包含：

1. Current Verdict：当前真正擅长什么。
2. Ceiling Blockers：限制最大能力的五个核心问题。
3. Benchmark Results：成功、失败、Repair 和 External Fallback。
4. Observer Findings：主 Agent 漏掉的过程问题。
5. Competitive Lessons：可迁移模式、直接来源和 License。
6. Priority Roadmap：P0/P1/P2/P3 与 Milestones。
7. Top 10 Backlog：证据与 Acceptance Criteria。
8. Measurement Plan：实施前必须建立的 Benchmark/Eval。
9. Risks、Non-goals、Unknowns。
10. Exact Artifact Paths、Commands、Stop Reason 和 Remaining Uncertainty。

每条重要结论明确标记：

- FACT：仓库、运行或来源直接证明；
- INFERENCE：由多个事实推导；
- RECOMMENDATION：未来行动；
- UNKNOWN：证据不足或冲突未解决。

完成标准不是“研究了很多工具”，而是：

- 真实执行了代表性 Benchmark；
- 保持 Observer 隔离；
- 记录失败、Fallback 和 Before/After Repair；
- 外部项目核验了一手来源、版本和 License；
- Gap 结论能追溯到 Evidence；
- Backlog 有优先级、复现步骤和验收测试；
- 没有修改源码和用户现有工作。

最后更新 run_manifest.json，写入最终状态、产物列表、Check Results、Observer 状态、Unresolved Conflicts 和精确 Stop Reason。

## Self-Review

- 双 Agent 在最终对账前保持隔离。
- Prompt 不要求或暗示读取隐藏推理。
- 允许生成审计产物，但禁止实现和源码修改。
- 外部 Fallback 被定义为能力缺口证据。
- 包含 Goal、Input、Execute、Checks、Feedback、Records、Stop、Human Gates 和 Acceptance。
- Backlog 每项均可复现、排序和验收。
