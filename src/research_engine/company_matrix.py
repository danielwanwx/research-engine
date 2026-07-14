"""Maintained public-company acceptance matrix for software-engineering targets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "software_engineering_company_matrix.v1"


_COMPANIES: tuple[dict[str, Any], ...] = (
    {"company": "Airbnb", "company_key": "airbnb", "official_domains": ["careers.airbnb.com", "airbnb.com"], "careers_search_url": "https://careers.airbnb.com/positions/?query={query}"},
    {"company": "Amazon", "company_key": "amazon", "official_domains": ["amazon.jobs"], "careers_search_url": "https://www.amazon.jobs/en/search?base_query={query}&loc_query={location}", "careers_api_url": "https://www.amazon.jobs/en/search.json?base_query={query}&loc_query={location}&result_limit=50&sort=relevant", "careers_api_provider": "amazon_jobs"},
    {"company": "Anthropic", "company_key": "anthropic", "official_domains": ["anthropic.com"], "ats": [{"provider": "greenhouse", "board_token": "anthropic"}]},
    {"company": "Apple", "company_key": "apple", "official_domains": ["jobs.apple.com", "apple.com"], "careers_search_url": "https://jobs.apple.com/en-us/search?search={query}&location={location}"},
    {"company": "Atlassian", "company_key": "atlassian", "official_domains": ["atlassian.com"], "careers_search_url": "https://www.atlassian.com/company/careers/all-jobs?search={query}"},
    {"company": "Block", "company_key": "block", "official_domains": ["block.xyz"], "careers_search_url": "https://block.xyz/careers/jobs?query={query}"},
    {"company": "Canva", "company_key": "canva", "official_domains": ["canva.com"], "careers_search_url": "https://www.canva.com/careers/jobs/?query={query}"},
    {"company": "Cloudflare", "company_key": "cloudflare", "official_domains": ["cloudflare.com"], "ats": [{"provider": "greenhouse", "board_token": "cloudflare"}]},
    {"company": "Coinbase", "company_key": "coinbase", "official_domains": ["coinbase.com"], "ats": [{"provider": "greenhouse", "board_token": "coinbase"}]},
    {"company": "Databricks", "company_key": "databricks", "official_domains": ["databricks.com"], "careers_search_url": "https://www.databricks.com/company/careers/open-positions?department=engineering&search={query}"},
    {"company": "DoorDash", "company_key": "doordash", "official_domains": ["careersatdoordash.com", "doordash.com"], "careers_search_url": "https://careersatdoordash.com/job-search/?keyword={query}"},
    {"company": "Figma", "company_key": "figma", "official_domains": ["figma.com"], "ats": [{"provider": "greenhouse", "board_token": "figma"}]},
    {"company": "Google", "company_key": "google", "official_domains": ["google.com"], "careers_search_url": "https://www.google.com/about/careers/applications/jobs/results/?q={query}&location={location}"},
    {"company": "Meta", "company_key": "meta", "official_domains": ["metacareers.com", "meta.com"], "careers_search_url": "https://www.metacareers.com/jobs?q={query}"},
    {"company": "Microsoft", "company_key": "microsoft", "official_domains": ["jobs.careers.microsoft.com", "microsoft.com"], "careers_search_url": "https://jobs.careers.microsoft.com/global/en/search?q={query}&lc={location}"},
    {"company": "Netflix", "company_key": "netflix", "official_domains": ["jobs.netflix.com", "netflix.com"], "careers_search_url": "https://jobs.netflix.com/search?q={query}"},
    {"company": "Notion", "company_key": "notion", "official_domains": ["notion.so"], "ats": [{"provider": "greenhouse", "board_token": "notion"}]},
    {"company": "NVIDIA", "company_key": "nvidia", "official_domains": ["nvidia.com"], "careers_search_url": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite?q={query}"},
    {"company": "OpenAI", "company_key": "openai", "official_domains": ["openai.com"], "careers_search_url": "https://openai.com/careers/search/?q={query}"},
    {"company": "Palantir", "company_key": "palantir", "official_domains": ["palantir.com"], "ats": [{"provider": "lever", "board_token": "palantir"}]},
    {"company": "Ramp", "company_key": "ramp", "official_domains": ["ramp.com"], "ats": [{"provider": "greenhouse", "board_token": "ramp"}]},
    {"company": "Reddit", "company_key": "reddit", "official_domains": ["redditinc.com"], "ats": [{"provider": "greenhouse", "board_token": "reddit"}]},
    {"company": "Roblox", "company_key": "roblox", "official_domains": ["careers.roblox.com", "roblox.com"], "careers_search_url": "https://careers.roblox.com/jobs?search={query}"},
    {"company": "Salesforce", "company_key": "salesforce", "official_domains": ["careers.salesforce.com", "salesforce.com"], "careers_search_url": "https://careers.salesforce.com/en/jobs/?search={query}"},
    {"company": "Shopify", "company_key": "shopify", "official_domains": ["shopify.com"], "careers_search_url": "https://www.shopify.com/careers/search?query={query}"},
    {"company": "Snowflake", "company_key": "snowflake", "official_domains": ["careers.snowflake.com", "snowflake.com"], "careers_search_url": "https://careers.snowflake.com/us/en/search-results?keywords={query}"},
    {"company": "Stripe", "company_key": "stripe", "official_domains": ["stripe.com"], "careers_search_url": "https://stripe.com/jobs/search?query={query}"},
    {"company": "Uber", "company_key": "uber", "official_domains": ["uber.com"], "careers_search_url": "https://www.uber.com/global/en/careers/list/?query={query}"},
)


def load_company_matrix() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "companies": deepcopy(list(_COMPANIES))}


def find_company(company: str) -> dict[str, Any] | None:
    key = "".join(character for character in company.lower() if character.isalnum())
    for row in _COMPANIES:
        row_key = "".join(character for character in str(row["company_key"]) if character.isalnum())
        if key == row_key:
            return deepcopy(row)
    return None
