"""FastAPI app: JSON API + the static web UI on the same server."""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import format_price, load_catalog
from app.chat_service import ChatRequest, answer, answer_events
from app.config import settings
from app.ingest import ensure_index
from app.vector_store import KNOWLEDGE, get_collection

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(title="Sherlock Combs Chatbot")


@app.on_event("startup")
def warm_up() -> None:
    """Fill the index at start-up (from the cache when possible) and load a local model,
    so the first chat message is not slow."""
    ensure_index()
    if settings.embedding_backend == "local":
        from app.embeddings import get_embedder

        get_embedder().embed_query("pemanasan")


@app.get("/health")
def health() -> dict:
    ensure_index()
    return {"status": "ok", "model": settings.gemini_model, "embedding": settings.embedding_backend,
            "chunks": get_collection(KNOWLEDGE).count(),
            "llm_configured": bool(settings.gemini_api_key)}


@app.get("/api/catalog")
def catalog() -> dict:
    cat = load_catalog()
    for group in ("services", "products"):
        for item in cat[group]:
            item["price_label"] = format_price(item["price"])
    return cat


def _validate(req: ChatRequest) -> None:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(req.message) > 1000:
        raise HTTPException(status_code=400, detail="Message is too long (max 1000 characters)")


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """Non-streaming endpoint (handy for curl and tests)."""
    _validate(req)
    ensure_index()
    return answer(req)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Streaming endpoint used by the web UI: one JSON event per line (NDJSON)."""
    _validate(req)
    ensure_index()  # serverless hosts may skip start-up events, so check here too

    def events():
        for ev in answer_events(req):
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
