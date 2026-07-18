"""Declarative recipes for bounded authenticated browser collection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

from research_engine.browser_auth import normalize_origin


@dataclass(frozen=True)
class SiteRecipe:
    recipe_id: str
    version: int
    platform: str
    display_name: str
    origins: tuple[str, ...]
    search_url_template: str
    item_selectors: tuple[str, ...]
    text_selectors: tuple[str, ...]
    title_selectors: tuple[str, ...] = ()
    author_selectors: tuple[str, ...] = ()
    time_selectors: tuple[str, ...] = ()
    link_selectors: tuple[str, ...] = ()
    login_markers: tuple[str, ...] = ()
    authenticated_markers: tuple[str, ...] = ()
    next_page_selectors: tuple[str, ...] = ()
    read_only_post_operations: tuple[str, ...] = ()
    fixture_verified: bool = True
    live_verified: bool = False

    def search_url(self, topic: str) -> str:
        if not self.search_url_template:
            return ""
        return self.search_url_template.format(query=quote_plus(str(topic).strip()))

    def accepts_url(self, url: str) -> bool:
        try:
            return normalize_origin(url) in {
                normalize_origin(origin) for origin in self.origins
            }
        except ValueError:
            return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "version": self.version,
            "platform": self.platform,
            "display_name": self.display_name,
            "origins": list(self.origins),
            "fixture_verified": self.fixture_verified,
            "live_verified": self.live_verified,
        }


RECIPES: tuple[SiteRecipe, ...] = (
    SiteRecipe(
        "linkedin", 1, "linkedin", "LinkedIn", ("https://www.linkedin.com",),
        "https://www.linkedin.com/search/results/content/?keywords={query}",
        ("div.feed-shared-update-v2", "li.reusable-search__result-container"),
        (".feed-shared-update-v2__description", ".entity-result__summary"),
        (".update-components-header__text-view", ".entity-result__title-text"),
        (".update-components-actor__name", ".entity-result__primary-subtitle"),
        ("time", ".update-components-actor__sub-description"),
        ("a.app-aware-link",),
        ("input[name='session_key']", ".authwall-join-form"),
        ("nav.global-nav", "button.global-nav__me-photo"),
    ),
    SiteRecipe(
        "x", 1, "x", "X", ("https://x.com",),
        "https://x.com/search?q={query}&src=typed_query&f=live",
        ("article[data-testid='tweet']",), ("div[data-testid='tweetText']",),
        author_selectors=("div[data-testid='User-Name']",), time_selectors=("time",),
        link_selectors=("a[href*='/status/']",),
        login_markers=("input[name='text']", "a[href='/login']"),
        authenticated_markers=("a[data-testid='AppTabBar_Home_Link']",),
        read_only_post_operations=("SearchTimeline", "TweetDetail"),
    ),
    SiteRecipe(
        "reddit", 1, "reddit", "Reddit", ("https://www.reddit.com",),
        "https://www.reddit.com/search/?q={query}&sort=new",
        ("shreddit-post", "article[data-testid='post-container']"),
        ("[slot='text-body']", "div[data-testid='post-content']"),
        ("[slot='title']", "h3"), ("[slot='authorName']", "a[data-testid='post_author_link']"),
        ("time",), ("a[slot='full-post-link']", "a[data-testid='post-title']"),
        ("faceplate-text-input[name='username']", "a[href*='/login']"),
        ("button[aria-label*='Open user menu']",),
    ),
    SiteRecipe(
        "blind", 1, "blind", "Blind", ("https://www.teamblind.com",),
        "https://www.teamblind.com/search/{query}",
        ("article", "[class*='feedItem']", "[class*='postItem']"),
        ("[class*='content']", "[class*='body']"), ("h2", "h3"),
        ("[class*='author']",), ("time",), ("a[href*='/post/']",),
        ("a[href*='/signin']", "input[type='email']"),
        ("a[href*='/my']", "button[aria-label*='profile']"),
    ),
    SiteRecipe(
        "glassdoor", 1, "glassdoor", "Glassdoor", ("https://www.glassdoor.com",),
        "https://www.glassdoor.com/Search/results.htm?keyword={query}",
        ("[data-test='review-details-container']", "[data-test='jobListing']"),
        ("[data-test='review-text']", "[data-test='descSnippet']"),
        ("[data-test='job-title']", "h2"), ("[data-test='employer-name']",),
        ("time",), ("a[data-test='job-link']", "a[href*='/Reviews/']"),
        ("input[name='username']", "button[data-test='signInButton']"),
        ("button[data-test='profileButton']",),
    ),
    SiteRecipe(
        "indeed", 1, "indeed", "Indeed", ("https://www.indeed.com",),
        "https://www.indeed.com/jobs?q={query}",
        (".job_seen_beacon", "[data-testid='slider_item']"),
        (".job-snippet", "[data-testid='jobsnippet_footer']"),
        ("h2.jobTitle",), ("[data-testid='company-name']", ".companyName"),
        ("span.date",), ("h2.jobTitle a",),
        ("input[type='email']", "a[href*='/account/login']"),
        ("a[href*='/account/view']", "button[aria-label*='Account']"),
    ),
    SiteRecipe(
        "onepointthreeacres", 1, "onepointthreeacres", "一亩三分地",
        ("https://www.1point3acres.com",),
        "https://www.1point3acres.com/bbs/search.php?mod=forum&srchtxt={query}",
        ("tbody[id^='normalthread_']", ".plhin"), (".t_f", ".xst"),
        ("a.xst",), (".authi a",), (".authi em",), ("a.xst",),
        ("input[name='username']", ".fastlg_l"), ("a[href*='space-uid']",),
        ("a.nxt",),
    ),
    SiteRecipe(
        "hackernews", 1, "hackernews", "Hacker News",
        ("https://hn.algolia.com", "https://news.ycombinator.com"),
        "https://hn.algolia.com/?q={query}", (".SearchResults_item", ".athing"),
        (".Story_title", ".titleline"), (".Story_title", ".titleline"),
        (".Story_author", ".hnuser"), (".Story_date", ".age"),
        (".Story_title a", ".titleline a"),
        next_page_selectors=(".morelink",),
    ),
    SiteRecipe(
        "github", 1, "github", "GitHub", ("https://github.com",),
        "https://github.com/search?q={query}&type=issues",
        (".Box-row", ".js-issue-row", "div.search-title"),
        (".mb-1", ".search-match"), ("a.Link--primary", "a.search-title"),
        ("a[data-hovercard-type='user']",), ("relative-time",),
        ("a.Link--primary", "a.search-title"),
        ("input[name='login']", "a[href='/login']"),
        ("summary[aria-label='View profile and more']",),
        ("a.next_page",),
    ),
    SiteRecipe(
        "stackoverflow", 1, "stackoverflow", "Stack Overflow",
        ("https://stackoverflow.com",),
        "https://stackoverflow.com/search?q={query}",
        (".s-post-summary", ".question-summary", ".answer"),
        (".s-post-summary--content-excerpt", ".post-text"),
        (".s-link", "h1 a"), (".s-user-card--link", ".user-details"),
        ("time", ".relativetime"), (".s-link", "h1 a"),
        ("input[name='email']", "a[href*='/users/login']"),
        ("a.my-profile", "a[href*='/users/current']"),
        ("a[rel='next']",),
    ),
)

GENERIC_RECIPE = SiteRecipe(
    "generic", 1, "web", "Generic authenticated site", (), "", ("article", "main"),
    ("p", "main"), ("h1", "h2"), link_selectors=("a[href]",),
    fixture_verified=False,
)

RECIPE_REGISTRY = {recipe.recipe_id: recipe for recipe in RECIPES}
PLATFORM_RECIPE_REGISTRY = {recipe.platform: recipe for recipe in RECIPES}


def get_recipe(recipe_id: str) -> SiteRecipe | None:
    normalized = str(recipe_id).strip().lower()
    return GENERIC_RECIPE if normalized == "generic" else RECIPE_REGISTRY.get(normalized)


def recipe_for_platform(platform: str) -> SiteRecipe | None:
    return PLATFORM_RECIPE_REGISTRY.get(str(platform).strip().lower())


def recipe_for_url(url: str) -> SiteRecipe | None:
    return next((recipe for recipe in RECIPES if recipe.accepts_url(url)), None)
