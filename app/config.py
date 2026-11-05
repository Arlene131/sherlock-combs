import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)  # values in .env always win over leftover terminal variables

ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    # LLM (Google Gemini)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")            # writes the answer
    gemini_fast_model: str = os.getenv("GEMINI_FAST_MODEL", "gemini-flash-lite-latest")  # profiling step
    thinking_level: str = os.getenv("THINKING_LEVEL", "minimal")  # less thinking = faster replies
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.4"))

    # Embeddings: "gemini" (API, light, deployable) or "local" (e5 on the server, needs ~1 GB RAM)
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "gemini")
    gemini_embedding_model: str = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    embedding_dim: int = int(os.getenv("EMBEDDING_DIM", "768"))
    local_embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

    # Vector DB (ChromaDB, persisted on disk)
    # On Vercel only /tmp is writable, so the index lives there (rebuilt from the cache on cold start).
    chroma_dir: str = os.getenv("CHROMA_DIR", "/tmp/chroma_db" if os.getenv("VERCEL") else str(ROOT_DIR / "chroma_db"))

    # Retrieval tuning
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "4"))
    rag_min_score: float = float(os.getenv("RAG_MIN_SCORE", "0.65"))
    faq_min_score: float = float(os.getenv("FAQ_MIN_SCORE", "0.88"))
    history_turns: int = int(os.getenv("HISTORY_TURNS", "6"))

    # Data files
    catalog_path: Path = ROOT_DIR / "data" / "catalog.json"
    faq_path: Path = ROOT_DIR / "data" / "faq.json"
    knowledge_dir: Path = ROOT_DIR / "data" / "knowledge"


settings = Settings()
