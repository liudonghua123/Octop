"""Unit tests for chunk inspection/adjustment and retrieval testing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge import service as service_module
from octop.infra.knowledge.index import KnowledgeIndex
from octop.infra.knowledge.service import KnowledgeService


@pytest.fixture
def env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[KnowledgeService, KnowledgeRepo, int]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repo = KnowledgeRepo(pool)
    owner = UserRepo(pool).create(username="owner", password_hash="h", role="user")
    services = SimpleNamespace(
        knowledge_repo=repo,
        settings_repo=SettingsRepo(pool),
    )
    return KnowledgeService(services), repo, owner


def _ready_document(repo: KnowledgeRepo, kb_id: str, filename: str = "doc.md") -> object:
    doc = repo.create_document(
        kb_id=kb_id, filename=filename, content_type="text/markdown", byte_size=1
    )
    repo.update_document(doc.id, status="ready", error_message="", chunk_count=1)
    return doc


def test_get_document_chunks_returns_stored_order(
    env: tuple[KnowledgeService, KnowledgeRepo, int],
) -> None:
    svc, repo, owner = env
    kb = repo.create_base(owner_user_id=owner, name="KB")
    doc = _ready_document(repo, kb.id)
    KnowledgeIndex(kb.id).replace_doc_chunks(
        doc.id, ["first chunk", "second chunk"], [[1.0, 0.0], [0.0, 1.0]]
    )

    payload = svc.get_document_chunks(kb.id, doc.id, actor_user_id=owner)

    assert payload["chunk_count"] == 2
    assert [c["text"] for c in payload["chunks"]] == ["first chunk", "second chunk"]
    assert [c["ordinal"] for c in payload["chunks"]] == [0, 1]
    assert payload["status"] == "ready"


def test_set_document_chunks_reembeds_and_replaces(
    env: tuple[KnowledgeService, KnowledgeRepo, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc, repo, owner = env
    kb = repo.create_base(owner_user_id=owner, name="KB")
    doc = _ready_document(repo, kb.id)
    KnowledgeIndex(kb.id).replace_doc_chunks(doc.id, ["old"], [[1.0, 0.0]])
    monkeypatch.setattr(service_module, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(
        service_module, "embed_knowledge_texts", lambda _s, texts: [[0.5, 0.5]] * len(texts)
    )

    updated = svc.set_document_chunks(kb.id, doc.id, ["new one", "new two"], actor_user_id=owner)

    assert updated.chunk_count == 2
    stored = svc.get_document_chunks(kb.id, doc.id, actor_user_id=owner)
    assert [c["text"] for c in stored["chunks"]] == ["new one", "new two"]


def test_set_document_chunks_rejects_empty(
    env: tuple[KnowledgeService, KnowledgeRepo, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc, repo, owner = env
    kb = repo.create_base(owner_user_id=owner, name="KB")
    doc = _ready_document(repo, kb.id)
    monkeypatch.setattr(service_module, "assert_knowledge_usable", lambda *_a: None)

    with pytest.raises(ValueError, match="non-empty"):
        svc.set_document_chunks(kb.id, doc.id, ["  "], actor_user_id=owner)


def test_test_retrieval_ranks_across_bases(
    env: tuple[KnowledgeService, KnowledgeRepo, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc, repo, owner = env
    kb_a = repo.create_base(owner_user_id=owner, name="A")
    kb_b = repo.create_base(owner_user_id=owner, name="B")
    doc_a = _ready_document(repo, kb_a.id, "a.md")
    doc_b = _ready_document(repo, kb_b.id, "b.md")
    KnowledgeIndex(kb_a.id).replace_doc_chunks(doc_a.id, ["alpha fact"], [[1.0, 0.0]])
    KnowledgeIndex(kb_b.id).replace_doc_chunks(doc_b.id, ["beta fact"], [[0.9, 0.1]])
    monkeypatch.setattr(service_module, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(service_module, "embed_knowledge_texts", lambda _s, texts: [[1.0, 0.0]])

    result = svc.test_retrieval([kb_a.id, kb_b.id], "alpha", actor_user_id=owner, k=5)

    assert result["query"] == "alpha"
    assert [h["text"] for h in result["hits"]][:1] == ["alpha fact"]
    assert result["hits"][0]["kb_id"] == kb_a.id
    assert result["hits"][0]["score"] >= result["hits"][1]["score"]
    assert result["base_coverage"] == {kb_a.id: 1, kb_b.id: 1}


def test_test_retrieval_requires_readable_base(
    env: tuple[KnowledgeService, KnowledgeRepo, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc, repo, owner = env
    other = UserRepo(repo._db).create(username="other", password_hash="h", role="user")
    kb = repo.create_base(owner_user_id=other, name="Private")
    monkeypatch.setattr(service_module, "assert_knowledge_usable", lambda *_a: None)

    with pytest.raises(PermissionError):
        svc.test_retrieval([kb.id], "query", actor_user_id=owner)


def test_test_retrieval_skips_unready_documents(
    env: tuple[KnowledgeService, KnowledgeRepo, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc, repo, owner = env
    kb = repo.create_base(owner_user_id=owner, name="KB")
    doc = repo.create_document(
        kb_id=kb.id, filename="pending.md", content_type="text/markdown", byte_size=1
    )
    KnowledgeIndex(kb.id).replace_doc_chunks(doc.id, ["ghost"], [[1.0, 0.0]])
    monkeypatch.setattr(service_module, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(service_module, "embed_knowledge_texts", lambda _s, texts: [[1.0, 0.0]])

    result = svc.test_retrieval([kb.id], "ghost", actor_user_id=owner)

    assert result["hits"] == []
    assert result["base_coverage"] == {kb.id: 0}
