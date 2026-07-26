# Applied AI Navigator Design

Date: 2026-07-25

## 1. Product Definition

Applied AI Navigator is a standalone personal intelligence and content system for
the `北美FDE实验室` brand.

Its first job is to act as the founder's Applied AI reading and research
delegate:

1. continuously scan high-value public and personalized sources;
2. identify important changes early;
3. read and verify the strongest signals;
4. explain them in Chinese;
5. connect them to companies, roles, technologies, customers, and business
   models;
6. help the founder learn and form an independent view.

Its second job is to turn selected research into original, reviewable public
content. Public content is optional. The daily intelligence output is mandatory.

The product promise is:

> 重大变化第一时间提醒；每天提供大量预消化信号；最重要的内容当天完成中文深读，并把其中少数信号转化为个人品牌资产。

The brand positioning is:

> 北美FDE实验室｜华语世界的 Applied AI 情报、职业与落地导航

The broader editorial promise is:

> Track how frontier AI becomes real customer value, what companies are
> building, what roles are emerging, and what practitioners should learn or do
> next.

## 2. Repository and System Boundaries

The implementation will live in a new sibling repository:

```text
/Users/danielwan/Project/
├── research-engine/
├── AgentProject/
│   └── Agentic Engineer/
└── applied-ai-navigator/
```

`research-engine` remains generic evidence infrastructure. It owns:

- public and authorized source collection;
- source normalization;
- evidence artifacts;
- duplicate, conflict, and quality checks;
- claim review;
- auditable research loop records.

It must not contain Xiaohongshu-specific business logic, the
`北美FDE实验室` author model, editorial policy, or publishing state.

`applied-ai-navigator` owns:

- signal scheduling and source policy;
- personalized browser sampling;
- Applied AI entities and relationships;
- topic selection;
- Research Engine orchestration;
- founder learning briefs;
- author memory and editorial strategy;
- content generation and novelty checking;
- Discord notifications and human handoffs;
- browser-assisted publishing;
- performance and product-opportunity feedback.

The previous `Agentic Engineer` project is a migration reference. Its source
registry, evidence concepts, review queue, SQLite patterns, and publishing
packages may inform the new implementation, but the new product will not be
implemented inside the old repository.

### 2.1 Research Engine Integration

The new project calls Research Engine through its stable CLI and artifact
contract:

```text
applied-ai-navigator
    -> research-engine run ...
    -> receives a run directory
    -> reads manifest, evidence, quality, claim, and loop artifacts
    -> builds an internal ResearchBrief
```

Required Research Engine artifacts are:

- `run_manifest.json`
- `evidence.jsonl`
- `evidence_quality.json`
- `claim_review.json`
- `loop_contract.json`
- `loop_record.json`

The Navigator must not import Research Engine implementation internals. A
Research Engine connector or implementation change should not require an
editorial-system rewrite.

## 3. Users and Outcomes

### 3.1 Primary User

The founder is the first user.

The system replaces the time-consuming work of:

- browsing X, LinkedIn, Xiaohongshu, forums, and official sites;
- opening and reading English source material;
- separating real changes from recycled commentary;
- translating difficult material into understandable Chinese;
- connecting new signals to existing knowledge;
- deciding which subjects deserve deeper study.

The founder should be able to understand the day's important Applied AI changes
in 10–15 focused minutes, while retaining the option to expand any item into its
full research evidence.

### 3.2 Public Audience

The public audience includes:

- North American SDE and Backend engineers;
- Data and ML practitioners;
- AI Engineer and FDE candidates;
- Applied AI builders;
- technical people evaluating an AI career transition;
- founders and operators interested in enterprise AI delivery.

They should learn:

- what is changing;
- why it matters;
- how Applied AI systems reach production;
- what customers and companies need;
- which roles and capabilities are gaining importance;
- what to learn, build, or investigate next.

### 3.3 Future Product Outcomes

The accumulated intelligence can support:

- an Applied AI company map;
- a live role and skills graph;
- JD gap diagnosis;
- FDE interview preparation;
- an industry use-case library;
- project and portfolio guidance;
- personalized career navigation;
- paid intelligence briefs;
- AI discovery and solution-blueprint tools.

## 4. Core Architecture

```text
Structured machine sources              Personalized browser sources
Official blogs                          X Following
Changelogs                              X Lists and searches
Documentation                           X For You
Careers and ATS                         LinkedIn feed and jobs
GitHub                                  Xiaohongshu follows and searches
HN, RSS, newsletters                    Reposts, bookmarks, manual links
             \                           /
              -> Unified Signal Inbox <-
                         |
                  Verification and dedupe
                         |
               Applied AI Knowledge Graph
                         |
                  Topic scoring and routing
                         |
                 Research Engine deep read
                         |
                 ResearchBrief quality gate
                    /                \
          Private Daily Brief       Editorial candidate
                    |                |
              Founder learning       Author Model
                                     |
                              Draft and critic loop
                                     |
                                Review Queue
                                     |
                         Browser-assisted preparation
                                     |
                              Founder publishes
                                     |
                        Performance and feedback
```

## 5. Hybrid Signal Radar

Browser automation is important but degradable. It is not the system's only
input.

### 5.1 Structured Sources

Structured or public collection is preferred for:

- official company blogs;
- product changelogs;
- documentation updates;
- official careers and ATS pages;
- GitHub releases, repositories, issues, and discussions;
- Hacker News;
- RSS feeds and newsletters;
- public research papers;
- public company announcements and customer cases.

Priority companies initially include:

- OpenAI;
- Anthropic;
- Palantir;
- Google;
- Microsoft;
- AWS;
- Databricks;
- Snowflake;
- NVIDIA;
- Scale AI;
- Mistral;
- Cognition;
- selected Applied AI startups.

The list is configuration, not hard-coded application behavior.

### 5.2 Personalized Browser Sources

Authorized Chrome access is used for:

- X Following;
- curated X Lists;
- bounded X For You sampling;
- focused X searches;
- LinkedIn feed;
- selected LinkedIn people and company pages;
- LinkedIn jobs;
- Xiaohongshu follows;
- Xiaohongshu Applied AI searches;
- the founder's reposts, bookmarks, and submitted links.

Browser scanning is bounded and auditable. It does not attempt unlimited
human-like scrolling.

Suggested bounds:

- X Following: posts from the last 12–24 hours;
- X Lists: 20–30 visible items per list per scan;
- X For You: at most two bounded scroll passes;
- focused searches: at most 10 candidates per query;
- LinkedIn and Xiaohongshu: bounded visible result windows;
- permanent deduplication by platform item ID and canonical URL.

Reposts, bookmarks, and manually submitted links receive a priority boost, but
they are not required to trigger the system.

### 5.3 Source Degradation

If Chrome, an extension, or a login is unavailable:

1. record the missing source and the last successful cursor;
2. continue collecting all healthy sources;
3. generate a coverage-qualified brief;
4. notify the founder through Discord;
5. resume from the saved cursor after human recovery;
6. avoid duplicate collection and duplicate content generation.

CAPTCHAs, login prompts, and account verification always require user action.

## 6. Scheduling and Volume

Applied AI Navigator is a real-time radar with daily synthesis.

### 6.1 Collection Cadence

- official, structured sources: every 15–30 minutes;
- X Lists and focused X searches: hourly;
- X Following and For You: 4–6 times per day;
- LinkedIn: 2–4 times per day;
- Xiaohongshu: 2–4 times per day;
- reposts, bookmarks, and manually submitted links: immediate priority;
- major verified signals: immediate Discord alert.

Exact platform cadence remains configurable so the system can respond to
stability, cost, and platform constraints.

### 6.2 Daily Output Funnel

The target daily funnel is:

```text
200–500 lightweight observations
        -> 20–50 pre-digested signal cards
        -> 8–12 priority brief items
        -> 3–5 Research Engine deep dives
        -> 1 private daily intelligence product
        -> 0–2 public content candidates
```

The system never invents a public topic solely to satisfy a daily posting
quota.

### 6.3 Brief Cadence

- 08:00: Morning Brief covering overnight changes;
- 12:00: Midday Delta containing only new material;
- 18:00: Evening Brief with the day's synthesis and recommended reading;
- anytime: high-impact breaking signal alerts.

All times use `America/Los_Angeles` unless configured otherwise.

## 7. Signal and Knowledge Model

### 7.1 Core Objects

#### Signal

A discrete external observation such as a post, official announcement, product
release, job opening, customer case, or document change.

#### Entity

A company, product, role, person, technology, industry, customer problem,
capability, or business model.

#### Topic

A researchable question or editorial opportunity that may combine multiple
signals. A signal is not automatically a topic.

#### ResearchRun

A Research Engine execution and its artifact directory.

#### ResearchBrief

The Navigator's structured, writing-safe representation of verified facts,
context, conflicts, unknowns, and candidate interpretations.

#### EditorialDecision

The record of why a topic should or should not become public content.

#### ContentDraft

A versioned title, body, caption, hashtag, and media package.

#### Review

The founder's approve, reject, edit, defer, or request-more-research decision.

#### PublishJob

The browser preparation and founder-confirmed publishing state.

#### Performance

Available post metrics and qualitative audience signals.

#### AuthorMemory

The founder's positioning, judgment patterns, approved language, rejected
language, historical edits, repeated arguments, and editorial preferences.

### 7.2 Object Flow

```text
many Signals
    -> one Topic
    -> one or more ResearchRuns
    -> one ResearchBrief
    -> one EditorialDecision
    -> multiple ContentDraft versions
    -> Review
    -> PublishJob
    -> Performance
    -> AuthorMemory and strategy updates
```

### 7.3 Processing States

```text
discovered
verified
enriched
clustered
scored
selected
researched
drafted
quality_passed
awaiting_review
approved
browser_prepared
published
measured
```

Terminal or side states include:

- `rejected`
- `duplicate`
- `needs_evidence`
- `deferred`
- `expired`
- `failed_retryable`
- `failed_terminal`
- `waiting_for_human`

### 7.4 Knowledge Storage

The first release uses SQLite for structured state and normal entity/relationship
tables. Large research artifacts remain in run directories.

A graph database is deferred until query complexity and scale demonstrate a
need. The conceptual graph still links:

- companies to products and teams;
- companies to roles and locations;
- roles to capabilities and responsibilities;
- technologies to customer problems;
- customer problems to industries and outcomes;
- signals and claims to source evidence;
- public content to the knowledge it used.

## 8. Research-First Production Loop

There is no public draft without a ResearchBrief.

### 8.1 Signal Verification

For each selected topic:

- locate the original publisher and source;
- verify date, version, and context;
- classify formal announcements, job signals, opinions, and marketing;
- search for contradictory or limiting evidence;
- prevent old information from being framed as a new trend.

An unverified secondary claim cannot be presented as fact.

### 8.2 Context Expansion

Research Engine investigates:

- relevant company history over the last 3–12 months;
- product, job, customer, and partnership evidence;
- comparable moves by other companies;
- whether the signal is isolated or part of a broader pattern;
- existing Chinese and English explanations;
- overlap with the founder's historical content;
- missing or underexplored interpretations.

### 8.3 ResearchBrief Contract

Each brief includes:

```yaml
signal:
  event:
  date:
  source:

verified_facts:
  - claim:
    source:
    confidence:

market_context:
company_context:
role_context:
technology_context:
customer_context:
business_context:

contrary_evidence:
unknowns:
source_coverage:
historical_account_overlap:

possible_angles:
  - angle:
    novelty:
    audience_value:
    evidence_strength:

recommended_angle:
why_now:
```

### 8.4 Research Quality Gate

The system evaluates:

- source class and confidence;
- duplicate pressure;
- missing facets;
- conflict flags;
- claim eligibility;
- research loop stop reason;
- coverage of primary sources;
- the boundary between facts and inference.

When quality is insufficient, the system may:

- narrow the claim;
- express an observation with uncertainty;
- schedule additional research;
- defer the topic;
- combine it with future evidence;
- reject public publication.

It must not force a conclusion to meet an output quota.

## 9. Private Intelligence Products

### 9.1 Rolling Signal Card

The 20–50 daily cards contain:

- event;
- source;
- one-sentence Chinese explanation;
- why it might matter;
- category;
- confidence;
- recommended next action.

### 9.2 Priority Brief Item

The 8–12 priority items add:

- company, role, technology, industry, and customer relationships;
- what is new relative to prior signals;
- whether the source deserves full reading;
- implications for the founder and audience.

### 9.3 Deep Dive

The 3–5 daily deep dives include:

- Chinese explanation of the original material;
- corroborating and conflicting evidence;
- technical implications;
- customer implications;
- business implications;
- role and career implications;
- links to prior knowledge;
- what remains uncertain;
- whether it is a public-content candidate.

## 10. Editorial System

### 10.1 Editorial Scope

The account covers seven long-term pillars:

1. `Applied AI Daily`: important product, company, and market changes;
2. `Company Radar`: what companies are building and betting on;
3. `Role Radar`: jobs, responsibilities, compensation, geography, and skills;
4. `Field Notes`: customer discovery, delivery, adoption, and failure;
5. `Tech Radar`: practical technology, tools, infrastructure, and safety;
6. `Business Radar`: ROI, business models, services, and product opportunities;
7. `Career Navigation`: learning, projects, interviews, and career decisions.

Loop Engineering is one Tech Radar topic and should not dominate the account.

### 10.2 Recommended Content Mix

- 25% company and industry movement;
- 20% roles, talent, and career maps;
- 20% technology and tool radar;
- 15% customer scenarios and industry cases;
- 10% business models, ROI, and product opportunities;
- 10% deep methods.

These are planning targets, not hard daily quotas.

### 10.3 Narrative Variety

Supported structures include:

- news explanation;
- customer case;
- concept lesson;
- product teardown;
- opinion and disagreement;
- practical guide;
- option comparison;
- future scenario.

The engine must not repeatedly use the pattern:

> People think X, but the real issue is Y.

### 10.4 Public Content Transformation

Every public candidate moves through:

1. `Signal`: what happened;
2. `Context`: where it sits in the Applied AI landscape;
3. `Interpretation`: the founder's evidence-grounded judgment;
4. `Implication`: effects on technology, companies, customers, and people;
5. `Action`: what readers should watch, learn, or validate next.

The system does not translate or summarize an English source paragraph by
paragraph. It creates a new explanation around a defensible thesis.

### 10.5 Novelty Rules

- one company should not occupy more than two posts in a week;
- a core technical thesis may not be repeated within 30 days;
- basic "why FDE is hot" and "how SDE moves to AI" topics are limited to one
  per month unless material new evidence changes the thesis;
- one narrative structure may not appear in consecutive posts;
- every public draft must add a new fact, relationship, framework, case, or
  judgment;
- terms such as `eval`, `trace`, `fallback`, `stop rule`, and `Loop` appear only
  when the topic requires them;
- news-only posts may not run for more than two consecutive publication days.

## 11. Author Model

The Author Model captures:

- Applied AI/FDE positioning;
- target audience;
- anti-hype and customer-value principles;
- preferred technical vocabulary;
- approved and rejected arguments;
- previously published topics and theses;
- repeated structures and overused phrases;
- founder edits to drafts;
- performance and audience feedback.

Writing "as the founder" means:

- selecting topics the founder values;
- applying the founder's judgment criteria;
- explaining material in the founder's calm, technical, opinionated voice.

It does not authorize fabricated experience. The system may not invent:

- customer engagements;
- deployments;
- interview experience;
- product usage;
- measured outcomes;
- employment history.

Without a verified personal experience, the draft may use language such as:

- "我的判断是";
- "更值得关注的是";
- "如果从 FDE 视角看".

## 12. Maker–Checker Content Loop

Public content uses separate roles:

- `Researcher`: builds verified context;
- `Strategist`: chooses audience, thesis, pillar, and format;
- `Writer`: produces the draft in the Author Model voice;
- `Critic`: checks facts, novelty, originality, repetition, and generic AI
  language.

The Critic cannot approve unsupported claims. Failed drafts return to research,
strategy, or writing depending on the failure.

The founder can review:

- original signals;
- core sources;
- fact and inference boundaries;
- why the angle was selected;
- novelty versus historical posts;
- the final content and media package.

## 13. Discord and Human Handoff

### 13.1 Channels

Suggested Discord channels are:

```text
#breaking-signals
#applied-ai-stream
#deep-research
#daily-brief
#content-review
#source-alerts
#research-requests
#system-status
```

### 13.2 Rollout

The first release uses a Discord webhook for one-way notifications. A later
Discord bot adds:

- buttons;
- feedback reactions;
- retry and skip commands;
- research requests;
- draft approval and rejection;
- task-resume commands.

### 13.3 Alerts

Immediate alerts cover:

- Chrome or extension unavailable;
- expired login;
- CAPTCHA or account verification;
- source-page structure changes;
- repeated connector failure;
- insufficient research evidence;
- failed content quality gate;
- unexpected publishing fields;
- a prepared post waiting for review.

### 13.4 Handoff Record

```yaml
handoff_id:
run_id:
source:
blocked_step:
reason:
last_successful_step:
required_human_action:
resume_step:
expires_at:
```

The system resumes from `resume_step`, not from the beginning.

No cookies, passwords, session tokens, or authentication codes are sent through
Discord.

## 14. Browser-Assisted Publishing

Publishing is semi-managed:

1. generate a complete, reviewed publish package;
2. open the authenticated Xiaohongshu creator page;
3. upload the selected assets;
4. fill title, body, caption, and hashtags;
5. verify the visible values;
6. stop before the final publication action;
7. require the founder to confirm and publish.

The system does not:

- click the final publish action;
- auto-comment;
- auto-message;
- simulate community interaction;
- bypass CAPTCHA or account verification.

## 15. Reliability, Recovery, and Observability

Every scheduled run has a stable `run_id`, idempotency keys, source cursors, and
checkpointed state.

The system records:

- requested and completed source scans;
- item counts and failure reasons;
- new, duplicate, and expired signals;
- research time, status, and cost;
- evidence quality and conflicts;
- brief completion time;
- accepted, edited, rejected, and deferred topics;
- browser handoffs and recovery time;
- publish preparation and founder confirmation;
- available post-performance signals.

No single unavailable browser source prevents healthy sources from completing.
The brief explicitly states its coverage gaps.

## 16. Delivery Phases

### Phase 1: Personal Intelligence Loop

Includes:

- structured and official sources;
- bounded personalized browser sources;
- Signal Inbox;
- Research Engine orchestration;
- ResearchBriefs;
- rolling cards, priority items, and deep dives;
- Applied AI knowledge storage;
- Discord notifications and handoffs;
- real-time alerts and three daily briefs.

Success criteria over seven consecutive days:

- briefs complete despite individual source degradation;
- no duplicate alerts for the same canonical event;
- the founder finds at least 1–3 genuinely useful items per day;
- facts, inference, conflicts, and coverage gaps are explicit;
- browser failures produce actionable Discord handoffs;
- the daily intelligence can be consumed in 10–15 focused minutes.

### Phase 2: Editorial and Xiaohongshu

Includes:

- editorial pillars and mix;
- Author Model;
- historical content import;
- EditorialDecision records;
- text and media packages;
- maker–checker generation;
- Discord content review;
- browser-assisted Xiaohongshu preparation;
- founder-confirmed publication.

Success criteria:

- every public claim is grounded in its ResearchBrief;
- repeated thesis and narrative checks work;
- drafts never fabricate personal experience;
- each post has identifiable original value;
- browser preparation fills the intended fields and stops before publication.

### Phase 3: Brand and Product Intelligence

Includes:

- performance feedback;
- comment and audience-demand analysis;
- company, role, skill, and product-opportunity maps;
- newsletters, podcast, and video scripts;
- a public Applied AI Navigator surface;
- personalized career products;
- multi-platform content reuse.

## 17. Explicit Non-Goals for the First Release

- unlimited crawling of every social platform;
- autonomous public-account operation;
- automated comments or private messages;
- automatic final publication;
- conclusions based only on low-quality secondary sources;
- a graph database before demonstrated need;
- full podcast or video production;
- forced daily public posting;
- multiple brands and social accounts.

## 18. Testing Strategy

### 18.1 Unit Tests

- canonicalization and deduplication;
- source scoring;
- state transitions;
- ResearchBrief construction;
- evidence-quality gating;
- novelty and historical-overlap checks;
- content-pillar routing;
- author-memory rules;
- Discord payload formatting;
- idempotency and cursor recovery.

### 18.2 Integration Tests

- Research Engine CLI and artifact contract;
- structured source to Signal Inbox;
- browser capture to normalized evidence;
- degraded-source brief generation;
- Discord webhook;
- review queue to browser preparation;
- resume after human handoff.

### 18.3 End-to-End Tests

- scheduled scan to Morning Brief;
- breaking official announcement to immediate Discord alert;
- X signal to verified deep dive;
- insufficient evidence to deferred topic;
- accepted topic to prepared Xiaohongshu page;
- browser-login failure to Discord handoff and successful resume;
- duplicate signal to no duplicate alert or draft.

### 18.4 Safety Tests

- no credential material in logs or Discord;
- no final publish action;
- no auto-comment or auto-message;
- no unsupported personal-experience claims;
- no claim marked factual without eligible evidence.

## 19. Acceptance Summary

Applied AI Navigator is successful when it:

1. continuously finds important Applied AI signals before the founder would
   normally have time to read them;
2. turns English and fragmented source material into useful Chinese
   understanding;
3. distinguishes facts, inference, conflict, and uncertainty;
4. compounds knowledge rather than repeating daily summaries;
5. creates varied, original public content only when evidence and novelty are
   sufficient;
6. degrades gracefully when browser sources fail;
7. brings the founder into the loop through Discord and final publish review;
8. accumulates reusable intelligence for future brand and product development.
