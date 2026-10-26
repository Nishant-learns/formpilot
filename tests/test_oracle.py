"""Official portal resolution, domain safety, and live-search fallback."""

from __future__ import annotations

import asyncio

from backend.core.oracle import PortalOracle
from backend.core.tinyfish_client import TinyFishError


class FakeSearchClient:
    def __init__(self, results=None, error=None):
        self.is_configured = True
        self._results = results or []
        self._error = error

    async def search(self, *args, **kwargs):
        if self._error:
            raise self._error
        return self._results


def test_registry_resolves_common_recruitment_queries():
    railway = PortalOracle.resolve_target("apply for railway ntpc")
    assert railway.official_verified is True
    assert railway.is_gov_domain is True
    assert "rrbapply.gov.in" in railway.target_url
    assert railway.domain_trust_score >= 95

    ssc = PortalOracle.resolve_target("ssc cgl 2026")
    assert "ssc.gov.in" in ssc.target_url

    bpsc = PortalOracle.resolve_target("bpsc bihar")
    assert "onlinebpsc.bihar.gov.in" in bpsc.target_url


def test_direct_official_url_is_audited():
    result = PortalOracle.resolve_target("https://ssc.gov.in/")

    assert result.resolved_via == "direct_url"
    assert result.official_verified is True
    assert result.is_gov_domain is True
    assert result.domain_trust_score == 99


def test_third_party_url_is_flagged():
    result = PortalOracle.resolve_target("https://example.com/some-application")

    assert result.is_gov_domain is False
    assert result.official_verified is False
    assert "not a verified government domain" in result.advisory.lower()


def test_third_party_recruitment_link_is_replaced_with_official_portal():
    result = PortalOracle.resolve_target("https://example.com/railway-ntpc-application")

    assert result.resolved_via == "domain_guard"
    assert "rrbapply.gov.in" in result.target_url
    assert "official government link" in result.advisory


def test_unknown_query_returns_an_unverified_result():
    result = PortalOracle.resolve_target("some entirely unknown recruitment board")

    assert result.resolved_via == "unverified"
    assert result.target_url == ""
    assert result.official_verified is False
    assert "Paste the official" in result.advisory


def test_empty_query_is_handled():
    result = PortalOracle.resolve_target("   ")
    assert result.resolved_via == "unverified"
    assert result.confidence == 0


def test_directory_contains_only_trusted_links():
    directory = PortalOracle.directory()

    assert directory
    for entry in directory:
        if entry["url"].startswith("http://127.0.0.1:8000/"):
            assert "Demo" in entry["name"]
        else:
            assert entry["url"].startswith("https://")
        assert entry["authority"]
        assert entry["keywords"]


def test_live_search_prefers_official_domains():
    client = FakeSearchClient(
        results=[
            {"title": "Aggregator", "url": "https://example.com/mystery-board-notification"},
            {"title": "Official Board", "url": "https://mysteryboard.gov.in/apply"},
        ]
    )

    result = asyncio.run(PortalOracle.resolve_target_live("mystery board notification", client))

    assert result.resolved_via == "tinyfish_search"
    assert result.target_url.startswith("https://mysteryboard.gov.in")
    assert result.official_verified is False  # search still needs human confirmation
    assert len(result.candidates) == 1


def test_live_search_without_official_result_returns_candidates():
    client = FakeSearchClient(
        results=[{"title": "Blog", "url": "https://example.com/blog"}]
    )

    result = asyncio.run(PortalOracle.resolve_target_live("mystery board", client))

    assert result.resolved_via == "unverified"
    assert result.target_url == ""
    assert len(result.candidates) == 1


def test_live_search_failure_is_user_safe():
    client = FakeSearchClient(error=TinyFishError("upstream unavailable"))

    result = asyncio.run(PortalOracle.resolve_target_live("mystery board", client))

    assert result.resolved_via == "unverified"
    assert "unavailable" in result.advisory.lower()


def test_unknown_query_without_a_configured_client_stays_local():
    class Unconfigured:
        is_configured = False

    result = asyncio.run(PortalOracle.resolve_target_live("mystery board", Unconfigured()))
    assert result.target_url == ""
    assert result.resolved_via == "unverified"
