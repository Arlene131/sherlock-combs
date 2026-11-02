"""The chat pipeline, step by step:

  1. FAQ check        - near-identical to a known FAQ? return its fixed answer (no LLM).
  2. Profiling        - fast LLM extracts intent + profile slots from the message.
  3. Slot check       - required info missing? ask the user (with guides) instead of guessing.
  4. Retrieval        - metadata-filtered search in ChromaDB.
  5. Generation       - LLM answers from context + full catalog (catalog grounding), streamed.
  6. Guardrail        - recommended IDs not in the catalog are dropped; prices come from catalog.

answer_events() yields events so the UI can show progress and stream text:
  {"type": "status", "text": ...}   {"type": "delta", "text": ...}   {"type": "done", ...result}
"""
import re
import time
from collections.abc import Iterator
from urllib.parse import quote_plus

from pydantic import BaseModel, Field

from app import llm, prompts
from app.catalog import catalog_as_prompt_text, to_cards
from app.config import settings
from app.profile import LABELS_ID, Extraction, Profile, describe, merge, missing_slots
from app.quick_extract import quick_extract
from app.retriever import get_guides, match_faq, retrieve

GREETING = re.compile(
    r"^\s*(?:halo|hallo|hai|hi|hey|hei|greetings|selamat\s+(?:pagi|siang|sore|malam))\b"
    r"(?:\s+(?:bro|sis|kak|gan|mas|bang|guys|kawan|sob|sobat|teman)\b)?\s*[!.,]*\s*",
    re.IGNORECASE,
)


def strip_greeting(text: str) -> str:
    stripped = GREETING.sub("", text, count=1)
    if stripped == text:
        return text
    return stripped[:1].upper() + stripped[1:]


MARKER = re.compile(r"\n?\s*\**REKOMENDASI\**\s*:(.*)$", re.IGNORECASE | re.DOTALL)
HOLD_BACK = 40  # characters kept back while streaming, so the marker line never flashes on screen


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    profile: Profile = Field(default_factory=Profile)
    seen_ids: list[str] = Field(default_factory=list)   # chunk ids already used in earlier answers
    last_intent: str | None = None                      # topic of the previous answer


def _mentioned_titles(ids: list[str]) -> list[str]:
    """Titles of styles/colours/treatments already shown (guides excluded), for 'opsi lain' requests."""
    if not ids:
        return []
    from app.retriever import GUIDE_CATEGORIES
    from app.vector_store import KNOWLEDGE, get_collection

    res = get_collection(KNOWLEDGE).get(ids=list(dict.fromkeys(ids)), include=["metadatas"])
    return [m["title"] for m in res["metadatas"] if m.get("category") not in GUIDE_CATEGORIES]


def examples_for(answer_text: str, hits: list[dict], limit: int = 4) -> list[dict]:
    """'Lihat contoh' links for every style/colour from the context that the answer actually mentions."""
    out, low = [], answer_text.lower()
    for h in hits:
        names = [n for n in h["metadata"].get("example_names", "").split("|") if n]
        found = next((n for n in names if re.search(rf"\b{re.escape(n.lower())}\b", low)), None)
        if found and all(e["id"] != h["id"] for e in out):
            query = h["metadata"]["example_query"]
            out.append({"id": h["id"], "label": found,
                        "url": "https://www.google.com/search?udm=2&q=" + quote_plus(query)})
    return out[:limit]


def _history_text(history: list[ChatMessage]) -> str:
    recent = history[-settings.history_turns:]
    return "\n".join(f"{'Pengguna' if m.role == 'user' else 'Sherlock'}: {m.content}" for m in recent)


def _sources(hits: list[dict]) -> list[dict]:
    return [{"id": h["id"], "title": h["metadata"].get("title", h["id"]), "score": h["score"],
             "filters": h.get("filters", [])} for h in hits]


def _context_text(hits: list[dict]) -> str:
    return "\n\n".join(f"[{h['id']}] {h['text']}" for h in hits) or "(tidak ada konteks relevan)"


def _done(answer, profile, route, intent=None, cards=None, sources=None, debug=None, examples=None) -> dict:
    return {"type": "done", "answer": answer, "profile": profile.model_dump(), "route": route,
            "intent": intent, "recommendations": cards or [], "examples": examples or [],
            "sources": sources or [], "debug": debug or {}}


def split_marker(text: str) -> tuple[str, list[str]]:
    """Separate the visible answer from the trailing 'REKOMENDASI: S01, P03' line."""
    match = MARKER.search(text)
    if not match:
        return text.strip(), []
    ids = re.findall(r"[SP]\d{2}", match.group(1).upper())
    return text[:match.start()].strip(), ids


def _stream_answer(system: str, prompt: str) -> Iterator[dict | tuple]:
    """Stream LLM text as delta events, hiding the marker line. Finally yields ('final', text)."""
    raw, emitted = "", 0
    for chunk in llm.stream_text(system, prompt):
        raw += chunk
        full = strip_greeting(raw)
        match = MARKER.search(full)
        safe_end = match.start() if match else max(emitted, len(full) - HOLD_BACK)
        if safe_end > emitted:
            yield {"type": "delta", "text": full[emitted:safe_end]}
            emitted = safe_end
    full = strip_greeting(raw)
    match = MARKER.search(full)
    end = match.start() if match else len(full)
    if end > emitted:
        yield {"type": "delta", "text": full[emitted:end]}
    yield ("final", full)


def answer_events(req: ChatRequest) -> Iterator[dict]:
    message = req.message.strip()
    history = _history_text(req.history)
    profile = req.profile
    timings: dict[str, float] = {}
    t = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal t
        now = time.perf_counter()
        timings[name] = round(now - t, 2)
        t = now

    # 1. FAQ shortcut
    faq = match_faq(message)
    lap("faq_check")
    if faq:
        yield _done(faq["answer"], profile, "faq", "faq",
                    sources=[{"id": faq["faq_id"], "title": faq["matched_question"],
                              "score": faq["score"], "filters": []}], debug={"timings_s": timings})
        return

    try:
        # 2. Profiling: keyword rules first (instant), LLM only when the rules are unsure
        ext = quick_extract(message, profile, req.last_intent)
        profiler = "rules"
        if ext is None:
            profiler = "llm"
            yield {"type": "status", "text": "Memahami pertanyaanmu…"}
            ext = llm.generate_json(
                prompts.EXTRACT_SYSTEM,
                prompts.build_extract_prompt(history, describe(profile), message),
                Extraction, temperature=0.0, model=settings.gemini_fast_model,
            )
        lap(f"profiling_{profiler}")
        profile = merge(profile, ext)
        intent = ext.intent
        search_query = ext.search_query or message
        yield {"type": "profile", "profile": profile.model_dump()}

        # 3. Slot check -> ask instead of guessing
        missing = [] if ext.wants_general_answer else missing_slots(intent, profile)
        if missing:
            guides = get_guides(missing)
            prompt = prompts.build_ask_prompt(history, describe(profile), message,
                                              ", ".join(LABELS_ID[m] for m in missing), _context_text(guides))
            final = ""
            for ev in _stream_answer(prompts.ASK_SYSTEM, prompt):
                if isinstance(ev, tuple):
                    final = ev[1]
                else:
                    yield ev
            lap("generation")
            text, _ = split_marker(final)
            yield _done(text, profile, "ask", intent, sources=_sources(guides),
                        debug={"missing": missing, "search_query": search_query, "timings_s": timings})
            return

        # 4. Retrieval
        yield {"type": "status", "text": "Mencari referensi…"}
        hits = retrieve(search_query, intent, profile, exclude=set(req.seen_ids),
                        alternatives=ext.wants_alternatives)
        lap("retrieval")

        # 5. Generation with catalog grounding (streamed)
        alt_note = prompts.alternatives_note(_mentioned_titles(req.seen_ids)) if ext.wants_alternatives else ""
        general_note = alt_note + (("CATATAN: pengguna tidak tahu sebagian profilnya, beri rekomendasi umum yang aman "
                                    "dan sarankan konsultasi gratis dengan barber.\n") if ext.wants_general_answer else "")
        prompt = prompts.build_answer_prompt(history, describe(profile), message, _context_text(hits),
                                             catalog_as_prompt_text(), general_note)
        final = ""
        for ev in _stream_answer(prompts.ANSWER_SYSTEM, prompt):
            if isinstance(ev, tuple):
                final = ev[1]
            else:
                yield ev
        lap("generation")
    except llm.LLMError as exc:
        yield _done("Maaf, Sherlock lagi gangguan koneksi ke AI. Coba lagi sebentar ya. "
                    f"(detail: {exc})", profile, "error", debug={"timings_s": timings})
        return
    except Exception as exc:  # never leave the UI hanging mid-stream
        yield _done(f"Maaf, terjadi kesalahan di server ({type(exc).__name__}). Coba lagi ya.",
                    profile, "error", debug={"timings_s": timings, "error": str(exc)})
        return

    # 6. Guardrail: only catalog items survive, prices from catalog
    text, ids = split_marker(final)
    yield _done(text, profile, "rag", intent, to_cards(ids), _sources(hits),
                debug={"search_query": search_query, "timings_s": timings,
                       "alternatives": ext.wants_alternatives},
                examples=examples_for(text, hits))


def answer(req: ChatRequest) -> dict:
    """Non-streaming helper: run the pipeline and return only the final result."""
    result = {}
    for ev in answer_events(req):
        if ev["type"] == "done":
            result = ev
    return result
