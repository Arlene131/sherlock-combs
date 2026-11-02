"""ChromaDB wrapper.

Two collections:
- "knowledge": hairstyle, colour, condition, treatment, guide, service, product chunks
- "faq": every FAQ question variant, pointing to its fixed answer

We compute embeddings ourselves (app.embeddings) and hand Chroma raw vectors,
so it is always clear which model produced them. Distance metric = cosine,
and Chroma returns distance = 1 - cosine_similarity.
"""
from functools import lru_cache

import chromadb

from app.config import settings

KNOWLEDGE = "knowledge"
FAQ = "faq"


@lru_cache
def get_client():
    return chromadb.PersistentClient(path=settings.chroma_dir)


def get_collection(name: str):
    return get_client().get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def reset_collection(name: str, embedding_id: str):
    """Delete and recreate a collection, remembering which embedding model filled it."""
    client = get_client()
    try:
        client.delete_collection(name)
    except Exception:
        pass
    return client.create_collection(name=name, metadata={"hnsw:space": "cosine", "embedding_id": embedding_id})


def index_is_current(embedding_id: str) -> bool:
    """True if both collections exist, are filled, and were built with the current embedding model."""
    for name in (KNOWLEDGE, FAQ):
        col = get_collection(name)
        if col.count() == 0 or (col.metadata or {}).get("embedding_id") != embedding_id:
            return False
    return True


def query(name: str, vector: list[float], k: int, where: dict | None = None) -> list[dict]:
    col = get_collection(name)
    res = col.query(
        query_embeddings=[vector],
        n_results=k,
        where=where or None,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for i, doc_id in enumerate(res["ids"][0]):
        hits.append({
            "id": doc_id,
            "text": res["documents"][0][i],
            "metadata": res["metadatas"][0][i],
            "score": round(1 - res["distances"][0][i], 4),
        })
    return hits
