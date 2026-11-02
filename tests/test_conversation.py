from app import chat_service, llm, prompts
from app.profile import Extraction, Profile
from app.quick_extract import quick_extract
from app.retriever import retrieve

ROUND = Profile(face_shape="round", hair_texture="straight", hair_thickness="thick")


def test_model_never_greets():
    assert "JANGAN menyapa" in prompts.conversation_status("")
    assert "JANGAN menyapa" in prompts.conversation_status("Pengguna: halo\nSherlock: halo juga")


def test_greeting_is_stripped_from_answers():
    assert chat_service.strip_greeting("Halo bro! wajah bulat cocok quiff.") == "Wajah bulat cocok quiff."
    assert chat_service.strip_greeting("Hai, coba quiff.") == "Coba quiff."
    assert chat_service.strip_greeting("Greetings! Quiff cocok.") == "Quiff cocok."
    assert chat_service.strip_greeting("Halodoc bukan sapaan") == "Halodoc bukan sapaan"
    assert chat_service.strip_greeting("Quiff cocok buat kamu.") == "Quiff cocok buat kamu."


def test_streamed_greeting_never_reaches_ui(monkeypatch):
    monkeypatch.setattr(llm, "stream_text", lambda *a, **k: iter(["Ha", "lo bro! ", "Quiff cocok.\nREKOMENDASI: S01"]))
    req = chat_service.ChatRequest(message="muka bulat rambut lurus, potong apa?")
    events = list(chat_service.answer_events(req))
    streamed = "".join(e["text"] for e in events if e["type"] == "delta")
    assert streamed == "Quiff cocok." and events[-1]["answer"] == "Quiff cocok."


def test_other_options_continues_topic():
    e = quick_extract("ada opsi lain nggak?", ROUND, last_intent="hairstyle")
    assert e.intent == "hairstyle" and e.wants_alternatives


def test_alternatives_skip_seen_styles_but_keep_guides():
    first = retrieve("gaya rambut wajah bulat lurus tebal", "hairstyle", ROUND)
    seen = {h["id"] for h in first}
    again = retrieve("gaya rambut wajah bulat lurus tebal", "hairstyle", ROUND, exclude=seen, alternatives=True)
    new_styles = [h["id"] for h in again if h["metadata"]["category"] == "hairstyle"]
    assert new_styles and not (set(new_styles) & seen)
    assert any(h["metadata"]["category"] == "face_guide" for h in again)


def test_examples_only_for_mentioned_styles():
    hits = retrieve("gaya rambut wajah bulat", "hairstyle", ROUND)
    hits += retrieve("quiff pompadour", "hairstyle", ROUND)
    ex = chat_service.examples_for("- **Quiff** — cocok karena volume atas.", hits)
    assert [e["label"] for e in ex] == ["Quiff"]
    assert ex[0]["url"].startswith("https://www.google.com/search?udm=2&q=quiff")


def test_chat_returns_examples_and_uses_alt_note(monkeypatch):
    captured = {}

    def fake_stream(system, prompt, model=None):
        captured["prompt"] = prompt
        return iter(["- **Faux Hawk** — tinggi di atas. Cocok kalau suka styling.\nREKOMENDASI: S01"])

    monkeypatch.setattr(llm, "stream_text", fake_stream)
    req = chat_service.ChatRequest(message="ada pilihan lain?", profile=ROUND, last_intent="hairstyle",
                                   seen_ids=["HS-quiff"],
                                   history=[chat_service.ChatMessage(role="user", content="muka bulat potong apa")])
    out = chat_service.answer(req)
    assert out["route"] == "rag" and out["debug"]["alternatives"]
    assert "OPSI LAIN" in captured["prompt"] and "Quiff" in captured["prompt"]
    assert "JANGAN menyapa" in captured["prompt"]
    assert all(s["id"] != "HS-quiff" for s in out["sources"])
