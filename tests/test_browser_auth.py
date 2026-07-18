import json
import stat

import pytest

from research_engine.browser_auth import (
    CapturePolicy,
    ConsentStore,
    browser_profile_key,
    clear_browser_profile,
    create_auth_challenge,
    normalize_origin,
)


def test_consent_is_exact_origin_and_recipe_versioned(tmp_path):
    store = ConsentStore(tmp_path)
    store.grant(recipe_id="linkedin", recipe_version=1, origin="https://www.linkedin.com/feed")

    assert store.has_consent(
        recipe_id="linkedin", recipe_version=1, origin="https://www.linkedin.com/search"
    )
    assert not store.has_consent(
        recipe_id="linkedin", recipe_version=2, origin="https://www.linkedin.com"
    )
    assert not store.has_consent(
        recipe_id="linkedin", recipe_version=1, origin="https://linkedin.com"
    )


def test_consent_revoke_and_owner_only_file(tmp_path):
    store = ConsentStore(tmp_path)
    store.grant(recipe_id="x", recipe_version=1, origin="https://x.com")
    store.grant(recipe_id="linkedin", recipe_version=1, origin="https://www.linkedin.com")

    assert store.revoke(recipe_id="x") == 1
    assert [grant["recipe_id"] for grant in store.list_grants()] == ["linkedin"]
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert json.loads(store.path.read_text())["schema_version"] == "browser_consents.v1"


def test_invalid_or_credentialed_origin_is_rejected():
    with pytest.raises(ValueError):
        normalize_origin("ftp://example.com")
    with pytest.raises(ValueError):
        normalize_origin("https://user:password@example.com")
    assert normalize_origin("https://EXAMPLE.com:443/path") == "https://example.com"


def test_auth_challenge_strips_query_and_is_stable():
    first = create_auth_challenge(
        recipe_id="linkedin",
        recipe_version=1,
        url="https://www.linkedin.com/search?q=secret&token=abc",
        reason="login_wall",
    )
    second = create_auth_challenge(
        recipe_id="linkedin",
        recipe_version=1,
        url="https://www.linkedin.com/search?q=other",
        reason="login_wall",
    )

    assert first.challenge_id == second.challenge_id
    assert first.requested_url == "https://www.linkedin.com/search"
    assert "secret" not in json.dumps(first.as_dict())


def test_capture_policy_denies_mutations_unknown_actions_and_cross_origin():
    policy = CapturePolicy.for_request(
        origins=("https://x.com",),
        max_results=2,
        depth="deep",
        read_only_post_operations=("SearchTimeline",),
    )

    assert policy.check_action("scroll") == (True, "allowed")
    assert policy.check_action("follow") == (False, "mutation_action_denied")
    assert policy.check_action("click_anything") == (False, "unknown_action_denied")
    assert policy.check_request(method="GET", url="https://x.com/search")[0]
    assert policy.check_request(method="GET", url="https://api.x.com/search") == (
        False,
        "cross_origin_denied",
    )
    assert policy.check_request(
        method="POST", url="https://x.com/i/api/graphql", operation="SearchTimeline"
    )[0]
    assert policy.check_request(
        method="POST", url="https://x.com/i/api/graphql", operation="CreateTweet"
    ) == (False, "write_request_denied")
    assert policy.max_pages == 2
    assert policy.max_scrolls == 3
    assert policy.timeout_seconds == 180


def test_clear_profile_only_removes_selected_recipe(tmp_path):
    linkedin = tmp_path / "profiles" / "linkedin"
    x_profile = tmp_path / "profiles" / "x"
    linkedin.mkdir(parents=True)
    x_profile.mkdir()
    (linkedin / "Preferences").write_text("fixture")

    assert clear_browser_profile("linkedin", root=tmp_path)
    assert not linkedin.exists()
    assert x_profile.exists()
    with pytest.raises(ValueError):
        clear_browser_profile("../x", root=tmp_path)


def test_generic_profiles_are_isolated_by_exact_origin(tmp_path):
    first_key = browser_profile_key("generic", origin="https://one.example/path")
    second_key = browser_profile_key("generic", origin="https://two.example/path")
    assert first_key != second_key
    first = tmp_path / "profiles" / first_key
    second = tmp_path / "profiles" / second_key
    first.mkdir(parents=True)
    second.mkdir()

    assert clear_browser_profile("generic", root=tmp_path, origin="https://one.example")
    assert not first.exists()
    assert second.exists()
