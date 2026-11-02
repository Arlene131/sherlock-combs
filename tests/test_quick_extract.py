from app.profile import Profile
from app.quick_extract import quick_extract

P = Profile()


def q(msg, profile=P):
    return quick_extract(msg, profile)


def test_hairstyle_with_slots():
    e = q("Muka aku bulat, rambut lurus tebal. Cocoknya potong gaya apa?")
    assert (e.intent, e.face_shape, e.hair_texture, e.hair_thickness) == ("hairstyle", "round", "straight", "thick")


def test_plain_haircut_request():
    e = q("saya mau potong rambut")
    assert e.intent == "hairstyle" and e.face_shape is None


def test_color_virgin_and_undertone():
    e = q("Undertone aku warm dan rambut belum pernah dicat, warna apa yang cocok?")
    assert (e.intent, e.undertone, e.hair_condition) == ("hair_color", "warm", ["virgin"])


def test_wish_is_not_history():
    e = q("mau bleaching rambut jadi silver")
    assert e.intent == "hair_color" and e.hair_condition == []


def test_history_detected():
    e = q("Pengen rambut silver, tapi rambutku pernah di-smoothing. Bisa nggak?")
    assert e.intent == "hair_color" and e.hair_condition == ["chemically_treated"]


def test_short_reply_infers_topic():
    e = q("wajahku kotak")
    assert e.intent == "hairstyle" and e.face_shape == "square"


def test_treatment():
    e = q("Rambutku rontok dan berketombe, perawatannya apa ya?")
    assert e.intent == "treatment" and set(e.issues) == {"hair_fall", "dandruff"}


def test_shop_questions_go_to_llm():
    assert q("harga potong rambut anak berapa?") is None
    assert q("jam buka berapa?") is None


def test_unknown_goes_to_llm():
    assert q("halo bro") is None


def test_catok_is_not_colored():
    e = q("rambut aku sering di catok, enaknya model apa")
    assert e.hair_condition == []
