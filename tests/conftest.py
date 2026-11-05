"""Test setup: a tiny fake embedder (bag-of-words hashing) so tests run offline
without downloading the real model, and a temporary ChromaDB folder."""
import hashlib
import os
import tempfile

import numpy as np
import pytest

os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="chroma_test_")


class FakeEmbedder:
    dim = 256

    def _vec(self, text: str):
        v = np.zeros(self.dim)
        for tok in text.lower().split():
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1
        n = np.linalg.norm(v)
        return (v / n if n else v).tolist()

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_queries(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


@pytest.fixture(scope="session", autouse=True)
def indexed():
    import app.embeddings as emb
    import app.retriever as ret
    from app import ingest

    fake = FakeEmbedder()
    emb.get_embedder = lambda: fake
    ret.get_embedder = lambda: fake
    ingest.ingest_knowledge(fake)
    ingest.ingest_faq(fake)
    yield


@pytest.fixture(autouse=True)
def allow_topic_judge(monkeypatch):
    """By default the LLM topic judge approves; security tests override this to simulate rejections."""
    from app import guard

    monkeypatch.setattr(guard, "judge_topic", lambda text, kind: guard.TopicVerdict(allowed=True))
