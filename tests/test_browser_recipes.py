import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from research_engine.browser_recipes import (
    GENERIC_RECIPE,
    RECIPES,
    get_recipe,
    recipe_for_platform,
    recipe_for_url,
)


EXPECTED = {
    "linkedin",
    "x",
    "reddit",
    "blind",
    "glassdoor",
    "indeed",
    "onepointthreeacres",
    "hackernews",
    "github",
    "stackoverflow",
}


def test_registry_has_exactly_the_approved_first_ten():
    assert {recipe.recipe_id for recipe in RECIPES} == EXPECTED
    assert len(RECIPES) == 10
    assert all(recipe.fixture_verified and not recipe.live_verified for recipe in RECIPES)


def test_recipe_urls_and_registry_resolution_are_stable():
    linkedin = get_recipe("linkedin")
    assert linkedin is not None
    assert linkedin.search_url("AI engineer") == (
        "https://www.linkedin.com/search/results/content/?keywords=AI+engineer"
    )
    assert recipe_for_url(linkedin.search_url("test")) == linkedin
    assert recipe_for_platform("linkedin") == linkedin
    assert recipe_for_url("https://evil.example/linkedin") is None


def test_every_recipe_has_capture_contract():
    for recipe in RECIPES:
        assert recipe.version >= 1
        assert recipe.origins
        assert recipe.search_url("fixture")
        assert recipe.item_selectors
        assert recipe.text_selectors
        assert recipe.accepts_url(recipe.search_url("fixture"))


def test_generic_fallback_is_not_claimed_as_fixture_verified():
    assert GENERIC_RECIPE.recipe_id == "generic"
    assert not GENERIC_RECIPE.fixture_verified
    assert get_recipe("generic") == GENERIC_RECIPE


def test_all_ten_recipe_fixtures_extract_visible_text():
    fixtures = json.loads(
        (Path(__file__).parent / "fixtures/browser_recipe_pages.json").read_text()
    )

    assert set(fixtures) == EXPECTED
    for recipe in RECIPES:
        fixture = fixtures[recipe.recipe_id]
        assert fixture["item_selector"] in recipe.item_selectors
        assert fixture["text_selector"] in recipe.text_selectors
        assert recipe.accepts_url(fixture["url"])
        root = ET.fromstring(f"<root>{fixture['html']}</root>")
        items = select_fixture(root, fixture["item_selector"])
        extracted = [
            " ".join("".join(node.itertext()).split())
            for item in items
            for node in select_fixture(item, fixture["text_selector"])
        ]
        assert fixture["expected_text"] in extracted


SIMPLE_SELECTOR = re.compile(
    r"^(?P<tag>[a-zA-Z][\w-]*)?(?:\.(?P<class>[\w-]+))?"
    r"(?:\[(?P<attr>[\w-]+)(?P<op>\^=|\*=|=)'(?P<value>[^']+)'\])?$"
)


def select_fixture(root, selector):
    """Small fixture-only matcher for the simple CSS contracts used above."""
    token = selector.split()[-1]
    match = SIMPLE_SELECTOR.fullmatch(token)
    assert match, f"fixture selector is outside the simple matcher: {selector}"
    matched = []
    for element in root.iter():
        if element is root:
            continue
        if match.group("tag") and element.tag != match.group("tag"):
            continue
        classes = set(element.attrib.get("class", "").split())
        if match.group("class") and match.group("class") not in classes:
            continue
        attr = match.group("attr")
        if attr:
            actual = element.attrib.get(attr, "")
            expected = match.group("value")
            operator = match.group("op")
            if operator == "=" and actual != expected:
                continue
            if operator == "^=" and not actual.startswith(expected):
                continue
            if operator == "*=" and expected not in actual:
                continue
        matched.append(element)
    return matched
