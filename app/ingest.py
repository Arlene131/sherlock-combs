"""Ingestion pipeline: knowledge JSON -> chunks -> embeddings -> ChromaDB.

Run once (and again whenever data/ changes):  python -m app.ingest
Re-running is safe: collections are rebuilt from scratch, so no duplicates.

Index cache: after embedding, the vectors are also saved to data/index_cache.json.
On a fresh server (e.g. every cold start on Vercel, where the disk is temporary) the
index is rebuilt from that file, so no embedding API calls and no rate limits at start-up.
The cache is only used when its fingerprint (data files + embedding model) still matches.
"""
import hashlib
import json

from app.config import settings
from app.embeddings import embedding_id, get_embedder
from app.knowledge import load_faq, load_knowledge_entries, to_documents
from app.vector_store import FAQ, KNOWLEDGE, index_is_current, reset_collection

CACHE_PATH = settings.knowledge_dir.parent / "index_cache.json"


def fingerprint() -> str:
    """Changes whenever a data file or the embedding model changes."""
    h = hashlib.sha256(embedding_id().encode())
    files = [settings.catalog_path, settings.faq_path, *sorted(settings.knowledge_dir.glob("*.json"))]
    for path in files:
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _faq_rows():
    ids, texts, metas = [], [], []
    for faq in load_faq():
        for i, q in enumerate(faq["questions"]):
            ids.append(f"{faq['id']}-q{i}")
            texts.append(q)
            metas.append({"faq_id": faq["id"], "answer": faq["answer"]})
    return ids, texts, metas


def _store(name: str, ids, texts, metas, vectors) -> None:
    col = reset_collection(name, embedding_id())
    col.add(ids=ids, documents=texts, metadatas=metas, embeddings=vectors)


def ingest_knowledge(embedder) -> dict:
    ids, texts, metas = to_documents(load_knowledge_entries())
    vectors = embedder.embed_passages(texts)
    _store(KNOWLEDGE, ids, texts, metas, vectors)
    return {"ids": ids, "texts": texts, "metas": metas, "vectors": vectors}


def ingest_faq(embedder) -> dict:
    ids, texts, metas = _faq_rows()
    # FAQ entries are questions, so embed them the same way as the user's question
    # (symmetric query-to-query matching), in one batch.
    vectors = embedder.embed_queries(texts)
    _store(FAQ, ids, texts, metas, vectors)
    return {"ids": ids, "texts": texts, "metas": metas, "vectors": vectors}


def _save_cache(knowledge: dict, faq: dict) -> None:
    def compact(rows):
        return {**rows, "vectors": [[round(float(x), 6) for x in v] for v in rows["vectors"]]}

    payload = {"fingerprint": fingerprint(), "embedding_id": embedding_id(),
               KNOWLEDGE: compact(knowledge), FAQ: compact(faq)}
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_from_cache() -> bool:
    """Rebuild ChromaDB from data/index_cache.json. Returns False if the cache is missing or stale."""
    if not CACHE_PATH.exists():
        return False
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if payload.get("fingerprint") != fingerprint():
        return False
    for name in (KNOWLEDGE, FAQ):
        rows = payload[name]
        _store(name, rows["ids"], rows["texts"], rows["metas"], rows["vectors"])
    return True


def main() -> None:
    embedder = get_embedder()
    knowledge = ingest_knowledge(embedder)
    faq = ingest_faq(embedder)
    _save_cache(knowledge, faq)
    print(f"Ingest done ({embedding_id()}): {len(knowledge['ids'])} knowledge chunks, "
          f"{len(faq['ids'])} FAQ question variants. Cache saved to {CACHE_PATH.name}.")


_ready = False


def ensure_index() -> None:
    """Make sure ChromaDB is filled: keep it, else load the cache, else embed everything."""
    global _ready
    if _ready:
        return
    if not index_is_current(embedding_id()):
        if load_from_cache():
            print("Index loaded from cache (no embedding API calls).")
        else:
            main()
    _ready = True


if __name__ == "__main__":
    main()
