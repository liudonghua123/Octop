"""Tests for aggregated multi-hub search and pre-install preview."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
async def env(env_with_main_agent):
    yield env_with_main_agent


# --- aggregated search ------------------------------------------------------


async def test_hub_search_all_merges_sources(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import skills as skills_router
    from octop.infra.skills import skillhub_market, skills_hub

    async def fake_skillhub_search(
        query: str,
        *,
        limit: int = 50,
        host: str | None = None,
        timeout: float = 10.0,
    ) -> list[dict[str, Any]]:
        return [
            {"slug": "file-reader", "name": "文件读取", "version": "1.0.0"},
        ]

    def fake_clawhub_search(
        query: str,
        limit: int = 20,
    ) -> list[skills_hub.HubSkillResult]:
        assert query == "file-reader"
        return [
            skills_hub.HubSkillResult(
                slug="file-reader",
                name="File Reader",
                description="read files",
                source="clawhub",
            ),
            skills_hub.HubSkillResult(
                slug="web-scraper",
                name="Web Scraper",
                source="clawhub",
            ),
        ]

    monkeypatch.setattr(skillhub_market, "search_skillhub", fake_skillhub_search)
    monkeypatch.setattr(skills_hub, "search_hub_skills", fake_clawhub_search)

    c, _srv, auth, aid = env
    r = await c.get(
        f"/api/agents/{aid}/skills/hub/search/all",
        headers=auth,
        params={"q": "file-reader"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    sources = {(row["source"], row["slug"]) for row in rows}
    assert ("skillhub", "file-reader") in sources
    assert ("clawhub", "web-scraper") in sources
    # Deduped: file-reader appears once per source, not merged blindly.
    assert len([row for row in rows if row["slug"] == "file-reader"]) == 2


async def test_hub_search_all_degrades_on_source_failure(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.skills import skillhub_market, skills_hub

    async def fake_skillhub_search(
        query: str,
        *,
        limit: int = 50,
        host: str | None = None,
        timeout: float = 10.0,
    ) -> list[dict[str, Any]]:
        return [{"slug": "only-skillhub", "name": "Only SkillHub"}]

    def failing_clawhub_search(
        query: str,
        limit: int = 20,
    ) -> list[skills_hub.HubSkillResult]:
        raise RuntimeError("clawhub unavailable")

    monkeypatch.setattr(skillhub_market, "search_skillhub", fake_skillhub_search)
    monkeypatch.setattr(skills_hub, "search_hub_skills", failing_clawhub_search)

    c, _srv, auth, aid = env
    r = await c.get(
        f"/api/agents/{aid}/skills/hub/search/all",
        headers=auth,
        params={"q": "query"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["slug"] == "only-skillhub"
    assert rows[0]["source"] == "skillhub"


async def test_hub_search_all_requires_auth(env: Any) -> None:
    c, _srv, _auth, aid = env
    r = await c.get(f"/api/agents/{aid}/skills/hub/search/all")
    assert r.status_code not in (200,), f"Expected auth failure, got {r.status_code}"


# --- pre-install preview -----------------------------------------------------


async def test_hub_preview_skillhub_skill(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.skills import skills_hub

    def fake_preview(slug: str, **kwargs: Any) -> tuple[str, str]:
        assert slug == "my-skill"
        return "my-skill", "---\nname: my-skill\n---\n\n# Hello"

    monkeypatch.setattr(skills_hub, "preview_skillhub_skill", fake_preview)

    c, _srv, auth, _aid = env
    r = await c.get(
        "/api/skills/hub/preview",
        headers=auth,
        params={"skill_name": "my-skill"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["name"] == "my-skill"
    assert "# Hello" in payload["content"]


async def test_hub_preview_bundle_url(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.skills import skills_hub

    def fake_preview_url(**kwargs: Any) -> tuple[str, str]:
        assert kwargs["bundle_url"] == "https://clawhub.ai/example-skill"
        return "example-skill", "---\nname: example\n---\n\nBody"

    monkeypatch.setattr(skills_hub, "preview_bundle_from_url", fake_preview_url)

    c, _srv, auth, _aid = env
    r = await c.get(
        "/api/skills/hub/preview",
        headers=auth,
        params={"bundle_url": "https://clawhub.ai/example-skill"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["name"] == "example-skill"
    assert "Body" in payload["content"]


async def test_hub_preview_rejects_unsupported_url(env: Any) -> None:
    c, _srv, auth, _aid = env
    r = await c.get(
        "/api/skills/hub/preview",
        headers=auth,
        params={"bundle_url": "https://evil.example.com/skill"},
    )
    assert r.status_code == 400


async def test_hub_preview_requires_params(env: Any) -> None:
    c, _srv, auth, _aid = env
    r = await c.get("/api/skills/hub/preview", headers=auth)
    assert r.status_code == 400


async def test_hub_preview_requires_auth(env: Any) -> None:
    c, _srv, _auth, _aid = env
    r = await c.get("/api/skills/hub/preview", params={"skill_name": "x"})
    assert r.status_code not in (200,), f"Expected auth failure, got {r.status_code}"


async def test_hub_preview_upstream_failure_maps_to_502(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.skills import skills_hub

    def failing_preview(slug: str, **kwargs: Any) -> tuple[str, str]:
        raise RuntimeError("hub down")

    monkeypatch.setattr(skills_hub, "preview_skillhub_skill", failing_preview)

    c, _srv, auth, _aid = env
    r = await c.get(
        "/api/skills/hub/preview",
        headers=auth,
        params={"skill_name": "broken"},
    )
    assert r.status_code == 502
