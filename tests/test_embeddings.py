from types import SimpleNamespace

import numpy as np

from app import embeddings


class FakeModels:
    def __init__(self):
        self.calls = []

    def embed_content(self, model, contents, config):
        self.calls.append((len(contents), config.task_type, config.output_dimensionality))
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0] + [0.0] * 766) for _ in contents])


def make(monkeypatch):
    fake = FakeModels()
    emb = embeddings.GeminiEmbedder.__new__(embeddings.GeminiEmbedder)
    emb.client, emb.model, emb.dim = SimpleNamespace(models=fake), "gemini-embedding-001", 768
    return emb, fake


def test_batches_normalises_and_uses_task_types(monkeypatch):
    emb, fake = make(monkeypatch)
    vecs = emb.embed_passages([f"t{i}" for i in range(120)])
    assert [c[0] for c in fake.calls] == [50, 50, 20]
    assert all(c[1] == "RETRIEVAL_DOCUMENT" and c[2] == 768 for c in fake.calls)
    assert np.isclose(np.linalg.norm(vecs[0]), 1.0) and np.isclose(vecs[0][0], 0.6)
    emb.embed_query("halo")
    emb.embed_query("halo")  # cached: no second API call
    assert fake.calls[-1][1] == "RETRIEVAL_QUERY" and len(fake.calls) == 4


def test_local_embedder_explains_missing_optional_dependency(monkeypatch):
    def missing_module(name):
        raise ModuleNotFoundError("No module named 'sentence_transformers'", name=name)

    monkeypatch.setattr(embeddings, "import_module", missing_module)

    try:
        embeddings.LocalE5Embedder("intfloat/multilingual-e5-small")
    except RuntimeError as exc:
        assert "pip install -r requirements-local.txt" in str(exc)
    else:
        raise AssertionError("Expected a helpful error when sentence-transformers is missing")
