from app import chat_service, llm
from app.catalog import items_by_id, to_cards
from app.knowledge import load_knowledge_entries
from app.profile import Extraction, Profile, merge, missing_slots
from app.retriever import match_faq, retrieve


def test_knowledge_references_only_catalog_items():
    entries = load_knowledge_entries()  # raises if an unknown ID is referenced
    assert len(entries) > 60


def test_cards_drop_unknown_ids_and_use_catalog_price():
    cards = to_cards(["S01", "X99", "p03", "S01"])
    assert [c["id"] for c in cards] == ["S01", "P03"]
    assert cards[0]["price"] == items_by_id()["S01"]["price"]


def test_merge_virgin_vs_processed():
    p = merge(Profile(hair_condition=["virgin"]), Extraction(intent="hair_color", hair_condition=["bleached"]))
    assert p.hair_condition == ["bleached"]


def test_missing_slots():
    assert missing_slots("hairstyle", Profile(face_shape="round")) == ["hair_texture"]
    assert missing_slots("hair_color", Profile(undertone="warm", hair_condition=["virgin"])) == []


def test_metadata_filter_respects_face_shape():
    hits = retrieve("gaya rambut wajah bulat rambut lurus", "hairstyle",
                    Profile(face_shape="round", hair_texture="straight"))
    styles = [h for h in hits if h["metadata"]["category"] == "hairstyle" and "face" in h.get("filters", [])]
    assert styles, "expected filtered hairstyle hits"
    assert all(h["metadata"].get("face_round") for h in styles)


def test_color_filter_respects_undertone():
    hits = retrieve("warna rambut undertone warm", "hair_color",
                    Profile(undertone="warm", hair_condition=["virgin"]))
    colors = [h for h in hits if h["metadata"]["category"] == "hair_color" and "undertone" in h.get("filters", [])]
    assert colors and all(h["metadata"].get("ut_warm") for h in colors)


def test_faq_exact_match():
    assert match_faq("Jam buka Sherlock Combs jam berapa?")["faq_id"] == "FAQ01"


def _patch_llm(monkeypatch, extraction, answer_text):
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: extraction)
    monkeypatch.setattr(llm, "stream_text", lambda *a, **k: iter([answer_text[:15], answer_text[15:]]))


def test_split_marker():
    text, ids = chat_service.split_marker("Coba quiff.\n**REKOMENDASI:** S01, p03, X9")
    assert text == "Coba quiff." and ids == ["S01", "P03"]


def test_chat_asks_when_slots_missing(monkeypatch):
    _patch_llm(monkeypatch, Extraction(intent="hairstyle", search_query="gaya rambut"),
               "Bentuk wajahmu seperti apa?")
    out = chat_service.answer(chat_service.ChatRequest(message="enaknya potong gaya apa ya bro"))
    assert out["route"] == "ask"
    assert set(out["debug"]["missing"]) == {"face_shape", "hair_texture"}


def test_chat_rag_streams_and_guards(monkeypatch):
    _patch_llm(monkeypatch,
               Extraction(intent="hairstyle", face_shape="round", hair_texture="straight",
                          search_query="gaya rambut wajah bulat lurus"),
               "Coba quiff dengan samping tipis ya.\nREKOMENDASI: S01, P03, S99")
    events = list(chat_service.answer_events(
        chat_service.ChatRequest(message="muka bulat rambut lurus, potong apa?")))
    streamed = "".join(e["text"] for e in events if e["type"] == "delta")
    done = events[-1]
    assert "REKOMENDASI" not in streamed and streamed.strip() == done["answer"]
    assert done["route"] == "rag" and done["profile"]["face_shape"] == "round"
    assert [c["id"] for c in done["recommendations"]] == ["S01", "P03"]
    assert "generation" in done["debug"]["timings_s"]
