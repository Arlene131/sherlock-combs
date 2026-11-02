"""Embedding backends.

- "gemini" (default): Google gemini-embedding-001 via API. No model runs on the server,
  so the app fits on small free hosting (e.g. Render free, 512 MB RAM).
- "local": intfloat/multilingual-e5-small with sentence-transformers (needs ~1 GB RAM,
  install requirements-local.txt). Good for offline experiments.

Both return L2-normalised vectors, so cosine similarity = dot product.
Documents and queries are embedded differently ("asymmetric" retrieval):
  gemini -> task_type RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY
  e5     -> prefix "passage: " vs "query: "
"""
import re
import time
from functools import lru_cache
from importlib import import_module

import numpy as np

from app.config import settings

BATCH_SIZE = 50  # texts per embedding API request
MAX_RETRIES = 4  # retries per batch when the free-tier rate limit (HTTP 429) is hit


def _normalise(vectors) -> list[list[float]]:
    arr = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (arr / norms).tolist()


class GeminiEmbedder:
    def __init__(self, model: str, dim: int):
        from google import genai

        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set; it is needed for Gemini embeddings.")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model, self.dim = model, dim

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        out = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            for attempt in range(MAX_RETRIES + 1):
                try:
                    res = self.client.models.embed_content(
                        model=self.model,
                        contents=batch,
                        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim),
                    )
                    break
                except Exception as exc:
                    # Free tier allows ~100 embedded texts per minute. When we hit that (HTTP 429),
                    # wait for the delay Google suggests and try the same batch again.
                    if "429" not in str(exc) or attempt == MAX_RETRIES:
                        raise
                    match = re.search(r"retry in ([\d.]+)s", str(exc))
                    wait = float(match.group(1)) + 1 if match else 60.0
                    print(f"Embedding rate limit reached, waiting {wait:.0f}s before retrying...", flush=True)
                    time.sleep(wait)
            out.extend(e.values for e in res.embeddings)
        # Gemini only pre-normalises full-size (3072-d) vectors, so normalise ourselves.
        return _normalise(out)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_QUERY")

    @lru_cache(maxsize=512)  # the same question is often embedded twice (FAQ check + retrieval)
    def _query_cached(self, text: str) -> tuple[float, ...]:
        return tuple(self._embed([text], "RETRIEVAL_QUERY")[0])

    def embed_query(self, text: str) -> list[float]:
        return list(self._query_cached(text))


class LocalE5Embedder:
    def __init__(self, model: str):
        try:
            sentence_transformers = import_module("sentence_transformers")
        except ModuleNotFoundError as exc:
            if exc.name != "sentence_transformers":
                raise
            raise RuntimeError(
                "Local embeddings require sentence-transformers. "
                "Install it with `pip install -r requirements-local.txt`."
            ) from exc

        self.model = sentence_transformers.SentenceTransformer(model)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode([f"passage: {t}" for t in texts], normalize_embeddings=True).tolist()

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode([f"query: {t}" for t in texts], normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(f"query: {text}", normalize_embeddings=True).tolist()


def embedding_id() -> str:
    """Identifies the vector space; the index is rebuilt automatically when this changes."""
    if settings.embedding_backend == "local":
        return f"local:{settings.local_embedding_model}"
    return f"gemini:{settings.gemini_embedding_model}:{settings.embedding_dim}"


@lru_cache
def get_embedder():
    if settings.embedding_backend == "local":
        return LocalE5Embedder(settings.local_embedding_model)
    return GeminiEmbedder(settings.gemini_embedding_model, settings.embedding_dim)