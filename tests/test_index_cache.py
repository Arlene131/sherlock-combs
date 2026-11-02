import json

from app import ingest
from app.vector_store import FAQ, KNOWLEDGE, get_collection, get_client


def test_cache_roundtrip_without_embedding_calls(tmp_path, monkeypatch):
    from tests.conftest import FakeEmbedder

    monkeypatch.setattr(ingest, "CACHE_PATH", tmp_path / "index_cache.json")
    monkeypatch.setattr(ingest, "get_embedder", lambda: FakeEmbedder())
    ingest.main()                                   # embeds + writes the cache
    assert (tmp_path / "index_cache.json").exists()

    # simulate a fresh serverless instance: empty DB, embedding API unavailable
    for name in (KNOWLEDGE, FAQ):
        get_client().delete_collection(name)

    def boom():
        raise AssertionError("embedding API must not be called when the cache is valid")

    monkeypatch.setattr(ingest, "get_embedder", boom)
    monkeypatch.setattr(ingest, "_ready", False)
    ingest.ensure_index()
    assert get_collection(KNOWLEDGE).count() == 96 and get_collection(FAQ).count() == 27


def test_stale_cache_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "index_cache.json"
    path.write_text(json.dumps({"fingerprint": "old"}))
    monkeypatch.setattr(ingest, "CACHE_PATH", path)
    assert ingest.load_from_cache() is False
