"""The chat pipeline, step by step:

  1. FAQ check        - near-identical to a known FAQ? return its fixed answer (no LLM).
  2. Profiling        - fast LLM extracts intent + profile slots from the message.
  3. Slot check       - required info missing? ask the user (with guides) instead of guessing.
  4. Retrieval        - metadata-filtered search in ChromaDB.
  5. Generation       - LLM answers from context + full catalog (catalog grounding); the answer is
                        validated by the output guard before it is sent to the UI.
  6. Guardrail        - recommended IDs not in the catalog are dropped; prices come from catalog.

Security (app/guard.py) wraps the whole pipeline: input guard before step 1, topic gate after step 2,
output guard during/after step 5. Blocked requests never reach the LLM.

answer_events() yields events so the UI can show progress and stream text:
  {"type": "status", "text": ...}   {"type": "delta", "text": ...}   {"type": "done", ...result}
"""
import re
import time
from collections.abc import Iterator
from urllib.parse import quote_plus

from pydantic import BaseModel, Field

from app import guard, llm, prompts
from app.catalog import catalog_as_prompt_text, to_cards
from app.config import settings
from app.profile import LABELS_ID, Extraction, Profile, describe, merge, missing_slots
from app.quick_extract import quick_extract
from app.retriever import get_guides, match_faq, retrieve

# Safety net: remove any greeting the model still writes at the start ("Halo bro!", "Hai,", "Greetings!").
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


class GuardViolation(Exception):
    pass


def _generate(system: str, prompt: str) -> str:
    """Collect the full LLM answer. Leaks/code abort generation immediately (output rules)."""
    raw = ""
    for chunk in llm.stream_text(system, prompt):
        raw += chunk
        reason = guard.output_violation(strip_greeting(raw))
        if reason:
            raise GuardViolation(reason)
    return strip_greeting(raw)


def _emit(text: str, size: int = 24) -> Iterator[dict]:
    """Send an already-validated answer to the UI in small pieces (typing effect)."""
    for i in range(0, len(text), size):
        yield {"type": "delta", "text": text[i:i + size]}


def _checked_answer(system: str, prompt: str) -> str:
    """Generate, then run the output guard BEFORE anything is shown. Returns the visible text."""
    final = _generate(system, prompt)
    visible, _ = split_marker(final)
    result = guard.output_guard.validate(visible)
    if not result.passed:
        raise GuardViolation(f"{result.validator}:{result.reason}"[:120])
    return final


def _blocked(profile, reason: str, timings=None) -> dict:
    return _done(guard.REFUSAL, profile, "blocked", debug={"blocked": reason, "timings_s": timings or {}})


def answer_events(req: ChatRequest) -> Iterator[dict]:
    message = req.message.strip()
    profile = req.profile

    # Security layer 1: rule-based input guard (no LLM call for anything suspicious)
    result = guard.input_guard_fast.validate(message)
    if not result.passed:
        yield _blocked(profile, result.reason)
        return
    if guard.is_greeting_only(message):
        yield _done(guard.GREETING_REPLY, profile, "greeting", "greeting")
        return
    # Security layer 2: history comes from the browser, so treat it as untrusted
    history = _history_text(guard.sanitize_history(req.history))
    # Security layer 6a: long / multi-line messages get an LLM topic judge before anything else
    if guard.is_risky(message):
        result = guard.input_guard_llm.validate(message)
        if not result.passed:
            yield _blocked(profile, f"input_{result.validator}")
            return
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

        # Security layer 3: topic gate
        if not ext.on_topic or (ext.intent in ("general", "greeting") and not guard.on_domain(message)):
            yield _blocked(req.profile, "off_topic", timings)
            return
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
            yield {"type": "status", "text": "Menyusun jawaban…"}
            final = _checked_answer(prompts.ASK_SYSTEM, prompt)
            lap("generation")
            text, _ = split_marker(final)
            yield from _emit(text)
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
        yield {"type": "status", "text": "Menyusun & memeriksa jawaban…"}
        final = _checked_answer(prompts.ANSWER_SYSTEM, prompt)
        lap("generation")
    except GuardViolation as exc:  # Security layers 5/6b: the output guard rejected the answer
        yield _blocked(profile, f"output_{exc}", timings)
        return
    except llm.LLMError as exc:
        print(f"LLM error: {exc}", flush=True)  # details go to the server log, never to the user
        yield _done("Maaf, Sherlock lagi gangguan koneksi ke AI. Coba lagi sebentar ya.",
                    profile, "error", debug={"timings_s": timings})
        return
    except Exception as exc:  # never leave the UI hanging mid-stream
        print(f"Server error: {type(exc).__name__}: {exc}", flush=True)
        yield _done("Maaf, terjadi kesalahan di server. Coba lagi ya.", profile, "error",
                    debug={"timings_s": timings})
        return

    # 6. Guardrail: only catalog items survive, prices from catalog (the answer already passed the output guard)
    text, ids = split_marker(final)
    yield from _emit(text)
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
