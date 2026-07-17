import json
from urllib.parse import parse_qs, urlsplit

from research_engine.connectors.github_public import GitHubPublicSearchConnector
from research_engine.connectors.github_public import build_github_request
from research_engine.connectors.github_public import normalize_github_query
from research_engine.models import CollectionRequest
from research_engine.runner import DEFAULT_CONNECTORS


def request():
    return CollectionRequest(
        source={
            "source_id": "github_public_search",
            "connector": "github_public_search",
            "query": "loop engineering",
        },
        topic="loop engineering",
        run_date="2026-06-27",
        depth="quick",
        max_results=2,
    )


def test_github_public_search_is_registered_by_default():
    assert DEFAULT_CONNECTORS["github_public_search"] is GitHubPublicSearchConnector


def test_normalize_github_query_removes_platform_planner_suffixes():
    assert normalize_github_query("#loop engineering github open source") == "loop engineering"


def test_github_public_search_normalizes_repository_rows(monkeypatch):
    def fake_fetch(query, *, max_results):
        assert query == "loop engineering"
        assert max_results == 2
        return {
            "total_count": 1,
            "items": [
                {
                    "full_name": "example/loopx",
                    "html_url": "https://github.com/example/loopx",
                    "description": "Loop engineering for long-running AI agents.",
                    "owner": {"login": "example"},
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-06-27T00:00:00Z",
                    "pushed_at": "2026-06-26T00:00:00Z",
                    "stargazers_count": 47,
                    "forks_count": 4,
                    "open_issues_count": 2,
                    "language": "Python",
                    "topics": ["loop-engineering", "ai-agents"],
                    "license": {"spdx_id": "Apache-2.0"},
                    "archived": False,
                    "default_branch": "main",
                }
            ],
        }

    monkeypatch.setattr("research_engine.connectors.github_public.fetch_github_repositories", fake_fetch)
    result = GitHubPublicSearchConnector().collect(request())

    assert result.warnings == []
    assert result.metadata["total_count"] == 1
    assert result.rows[0]["connector"] == "github_public_search"
    assert result.rows[0]["platform"] == "github"
    assert result.rows[0]["title"] == "example/loopx"
    assert result.rows[0]["url"] == "https://github.com/example/loopx"
    assert result.rows[0]["metrics"]["stars"] == 47
    assert result.rows[0]["license_spdx"] == "Apache-2.0"
    assert result.rows[0]["archived"] is False
    assert result.rows[0]["pushed_at"] == "2026-06-26T00:00:00Z"
    assert result.rows[0]["default_branch"] == "main"
    assert result.rows[0]["raw_api_rank"] == 1
    assert result.rows[0]["engine_rank"] == 1
    assert "Loop engineering" in result.rows[0]["text"]


def test_github_request_uses_best_match_and_optional_environment_auth(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "github_pat_secret")

    request_value = build_github_request("research agent", max_results=12)
    query = parse_qs(urlsplit(request_value.full_url).query)

    assert query == {"q": ["research agent"], "per_page": ["12"]}
    assert request_value.get_header("Authorization") == "Bearer github_pat_secret"


def test_github_public_search_redacts_secret_like_payload(monkeypatch):
    def fake_fetch(query, *, max_results):
        return {
            "items": [
                {
                    "full_name": "example/private-ref",
                    "html_url": "https://github.com/example/private-ref?access_token=secret-token",
                    "description": "Visible token=payload-secret",
                    "owner": {"login": "example"},
                }
            ]
        }

    monkeypatch.setattr("research_engine.connectors.github_public.fetch_github_repositories", fake_fetch)
    result = GitHubPublicSearchConnector().collect(request())
    serialized = json.dumps(result.rows[0], ensure_ascii=False)

    assert "secret-token" not in serialized
    assert "payload-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_audit_enrichment_is_explicit_and_bounded(monkeypatch):
    def fake_fetch(query, *, max_results):
        return {
            "items": [
                {
                    "full_name": f"example/project-{index}",
                    "html_url": f"https://github.com/example/project-{index}",
                    "description": "loop engineering agent",
                }
                for index in range(6)
            ]
        }

    enriched = []

    def fake_enrich(full_name):
        enriched.append(full_name)
        return {"contributors": ["octocat"]}

    monkeypatch.setattr("research_engine.connectors.github_public.fetch_github_repositories", fake_fetch)
    monkeypatch.setattr("research_engine.connectors.github_public.enrich_github_repository", fake_enrich)
    base = request()
    audit_request = CollectionRequest(
        source={**base.source, "enrich_github": True, "enrichment_limit": 10},
        topic=base.topic,
        run_date=base.run_date,
        depth="audit",
        max_results=6,
    )

    result = GitHubPublicSearchConnector().collect(audit_request)

    assert len(enriched) == 3
    assert all("github_enrichment" in row for row in result.rows[:3])
    assert all("github_enrichment" not in row for row in result.rows[3:])
