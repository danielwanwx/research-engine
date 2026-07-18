"""Generic platform coverage planning for broad research runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any
from urllib.parse import quote_plus


@dataclass(frozen=True)
class PlatformProfile:
    platform: str
    label: str
    category: str
    access_mode: str
    preferred_connector: str
    search_url_template: str = ""
    query_suffixes: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ("broad", "deep", "all")
    requires_login: bool = False
    risk: str = "medium"
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


PLATFORM_PROFILES: tuple[PlatformProfile, ...] = (
    PlatformProfile(
        platform="web",
        label="Open web",
        category="web",
        access_mode="public",
        preferred_connector="web_page_or_agent_reach",
        search_url_template="https://www.google.com/search?q={query}",
        query_suffixes=("latest evidence", "official source", "primary data"),
        scopes=("quick", "broad", "deep", "all"),
    ),
    PlatformProfile(
        platform="x",
        label="X / Twitter",
        category="social",
        access_mode="logged_in_or_agent_reach",
        preferred_connector="agent_reach_or_external",
        search_url_template="https://x.com/search?q={query}&src=typed_query&f=live",
        query_suffixes=("discussion", "thread", "checks"),
        requires_login=True,
    ),
    PlatformProfile(
        platform="reddit",
        label="Reddit",
        category="forum",
        access_mode="public_or_agent_reach",
        preferred_connector="agent_reach_or_external",
        search_url_template="https://www.reddit.com/search/?q={query}&sort=new",
        query_suffixes=("site:reddit.com discussion", "reddit comments"),
        scopes=("quick", "broad", "deep", "all"),
    ),
    PlatformProfile(
        platform="hackernews",
        label="Hacker News",
        category="forum",
        access_mode="public",
        preferred_connector="web_or_external",
        search_url_template="https://hn.algolia.com/?q={query}",
        query_suffixes=("hacker news", "hn discussion"),
        scopes=("quick", "broad", "deep", "all"),
    ),
    PlatformProfile(
        platform="github",
        label="GitHub",
        category="developer",
        access_mode="public_or_gh_auth",
        preferred_connector="agent_reach_or_external",
        search_url_template="https://github.com/search?q={query}&type=repositories&s=updated&o=desc",
        query_suffixes=("github", "open source", "repo"),
        scopes=("quick", "broad", "deep", "all"),
    ),
    PlatformProfile(
        platform="youtube",
        label="YouTube",
        category="video",
        access_mode="public",
        preferred_connector="agent_reach_or_external",
        search_url_template="https://www.youtube.com/results?search_query={query}",
        query_suffixes=("youtube", "interview", "presentation"),
    ),
    PlatformProfile(
        platform="linkedin",
        label="LinkedIn",
        category="professional",
        access_mode="logged_in_browser_or_external",
        preferred_connector="external_authorized_capture",
        search_url_template="https://www.linkedin.com/search/results/content/?keywords={query}",
        query_suffixes=("linkedin", "hiring", "company posts"),
        requires_login=True,
    ),
    PlatformProfile(
        platform="xiaohongshu",
        label="Xiaohongshu",
        category="china_social",
        access_mode="logged_in_browser_or_agent_reach",
        preferred_connector="agent_reach_or_external",
        search_url_template="https://www.xiaohongshu.com/search_result?keyword={query}",
        query_suffixes=("小红书", "真实体验", "讨论"),
        requires_login=True,
    ),
    PlatformProfile(
        platform="bilibili",
        label="Bilibili",
        category="china_video",
        access_mode="public_or_agent_reach",
        preferred_connector="agent_reach_or_external",
        search_url_template="https://search.bilibili.com/all?keyword={query}",
        query_suffixes=("bilibili", "B站", "视频"),
        scopes=("deep", "all"),
    ),
    PlatformProfile(
        platform="weibo",
        label="Weibo",
        category="china_social",
        access_mode="logged_in_or_agent_reach",
        preferred_connector="agent_reach_or_external",
        search_url_template="https://s.weibo.com/weibo?q={query}",
        query_suffixes=("微博", "热议"),
        scopes=("deep", "all"),
        requires_login=True,
    ),
    PlatformProfile(
        platform="wechat",
        label="WeChat Articles",
        category="china_content",
        access_mode="agent_reach_or_external",
        preferred_connector="agent_reach_or_external",
        search_url_template="https://weixin.sogou.com/weixin?type=2&query={query}",
        query_suffixes=("公众号", "微信文章", "深度分析"),
        scopes=("deep", "all"),
    ),
    PlatformProfile(
        platform="v2ex",
        label="V2EX",
        category="forum",
        access_mode="public",
        preferred_connector="agent_reach_or_web",
        search_url_template="https://www.google.com/search?q={query}+site%3Av2ex.com",
        query_suffixes=("site:v2ex.com", "V2EX"),
        scopes=("deep", "all"),
    ),
    PlatformProfile(
        platform="xueqiu",
        label="Xueqiu",
        category="finance_social",
        access_mode="authorized_session_or_external",
        preferred_connector="agent_reach_or_external",
        search_url_template="https://xueqiu.com/k?q={query}",
        query_suffixes=("雪球", "投资者讨论"),
        scopes=("deep", "all"),
        requires_login=True,
    ),
    PlatformProfile(
        platform="lenny",
        label="Lenny Newsletter",
        category="newsletter",
        access_mode="external_authorized_capture",
        preferred_connector="external_jsonl",
        search_url_template="https://www.google.com/search?q={query}+site%3Alennysnewsletter.com",
        query_suffixes=("Lenny newsletter", "founder operator discussion"),
        requires_login=True,
    ),
    PlatformProfile(
        platform="rss",
        label="RSS / Atom",
        category="feed",
        access_mode="public",
        preferred_connector="rss_or_external",
        query_suffixes=("rss", "official blog", "changelog"),
        scopes=("quick", "broad", "deep", "all"),
    ),
)


def build_platform_research_plan(
    topic: str,
    *,
    scope: str = "broad",
    pack: dict[str, Any] | None = None,
    depth: str = "quick",
) -> list[dict[str, Any]]:
    normalized_scope = scope if scope in {"quick", "broad", "deep", "all"} else "broad"
    pack_platforms = pack_platforms_for_depth(pack, depth)
    plan: list[dict[str, Any]] = []
    for profile in PLATFORM_PROFILES:
        if normalized_scope not in profile.scopes and profile.platform not in pack_platforms:
            continue
        query = platform_query(topic, profile, pack=pack)
        plan.append(
            {
                **profile.as_dict(),
                "query": query,
                "search_url": profile.search_url_template.format(query=quote_plus(query))
                if profile.search_url_template
                else "",
                "enabled_by_default": profile.platform in {"web", "github", "hackernews", "reddit"}
                or profile.platform in pack_platforms,
            }
        )
    return plan


def pack_platforms_for_depth(
    pack: dict[str, Any] | None,
    depth: str,
) -> set[str]:
    """Return always-on pack platforms plus the platforms enabled for this depth."""
    resolved = pack or {}
    platforms = {str(platform) for platform in resolved.get("platforms") or []}
    depth_platforms = resolved.get("platforms_by_depth") or {}
    if isinstance(depth_platforms, dict):
        platforms.update(str(platform) for platform in depth_platforms.get(depth) or [])
    return platforms


def platform_query(
    topic: str,
    profile: PlatformProfile,
    *,
    pack: dict[str, Any] | None = None,
) -> str:
    browser_queries = (pack or {}).get("browser_queries") or {}
    if isinstance(browser_queries, dict) and profile.platform in browser_queries:
        return compact_query(str(browser_queries[profile.platform]))
    suffix = " ".join(profile.query_suffixes[:2])
    return compact_query(f"{topic} {suffix}".strip())


def compact_query(query: str, *, limit: int = 120) -> str:
    return re.sub(r"\s+", " ", query).strip()[:limit].strip()
