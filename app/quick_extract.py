"""Fast, rule-based profiling (no LLM call).

Most messages use a small, predictable vocabulary ("wajah bulat", "rambut lurus",
"undertone warm", "ketombe"), so keyword rules can extract intent and slots in
microseconds. If the rules are not confident (no intent found, or the message is
about prices/opening hours/etc.), we return None and the LLM does the profiling.
"""
import re

from app.profile import Extraction, Profile, describe

FACE = [
    (r"\b(oval)\b", "oval"),
    (r"\b(bulat|bundar|chubby|tembem)\b", "round"),
    (r"\b(kotak|persegi(?! panjang)|square)\b", "square"),
    (r"\b(lonjong|persegi panjang|oblong|panjang)\b", "oblong"),
    (r"\b(hati|heart|love)\b", "heart"),
    (r"\b(diamond|berlian|belah ketupat)\b", "diamond"),
    (r"\b(segitiga|triangle|pear)\b", "triangle"),
]
TEXTURE = [
    (r"\b(keriting|kriting|curly|kribo)\b", "curly"),
    (r"\b(bergelombang|gelombang|wavy|ikal)\b", "wavy"),
    (r"\b(lurus|straight)\b", "straight"),
]
THICKNESS = [
    (r"\b(tipis|jarang|thin)\b", "thin"),
    (r"\b(tebal|tebel|lebat|mengembang|thick)\b", "thick"),
    (r"\b(sedang|normal)\b", "medium"),
]
UNDERTONE = [
    (r"\b(warm|hangat)\b|urat\w* (hijau|ijo)|cocok (pakai )?emas", "warm"),
    (r"\b(cool|dingin)\b|urat\w* (biru|ungu)|cocok (pakai )?perak", "cool"),
    (r"\b(neutral|netral)\b", "neutral"),
]
VIRGIN = r"\bvirgin\b|belum pernah (di)?(cat|warna|semir|bleach|apa.?apa)|rambut asli|natural belum"

PAST = r"(pernah|sudah|udah|bekas|habis|abis|sempat|baru)\s+(\w+\s+){0,2}(di-?)?"
CONDITION = [
    (PAST + r"(bleach|bleaching|blich)", "bleached"),
    (PAST + r"(smoothing|rebonding|keratin|perm|catok permanen)", "chemically_treated"),
    (PAST + r"(cat|semir|warna|henna)", "colored"),
    (r"\b(rusak|kering|bercabang|kasar|mudah patah|kayak jerami)\b", "damaged"),
    (r"\b(uban|beruban)\b", "gray"),
]
ISSUES = [
    (r"ketombe", "dandruff"),
    (r"\b(rontok|botak|kerontokan)\w*", "hair_fall"),
    (r"\b(frizz|frizzy|kusut)\b", "frizzy"),
    (r"\b(berminyak|minyakan|lepek)\b", "oily"),
    (r"\b(samping (mekar|berdiri|ngembang)|mekar)\b", "side_puff"),
    (r"\b(jenggot|brewok|kumis|cukur (jenggot|kumis|bersih))\b", "beard"),
]

INTENTS = [
    ("hair_color", r"\b(warna|cat|semir|bleach\w*|highlight|balayage|ombre|silver|blonde|ash|coloring|mewarnai)\b"),
    ("treatment", r"\b(rawat|perawatan|treatment|ketombe|rontok|kering|rusak|spa|creambath|jenggot|kumis|frizz)\w*"),
    ("product", r"\b(pomade|clay|powder|sampo|shampoo|tonik|tonic|vitamin|serum|beard oil|produk|conditioner)\b"),
    ("hairstyle", r"\b(potong|potongan|gaya|model|style|cukur rambut|haircut|cocok(nya)? (apa|gimana))\b"),
]

SHOP = r"\b(harga|berapa|biaya|jam|buka|tutup|alamat|lokasi|booking|reservasi|bayar|qris|debit|antri)\b"
GENERAL = r"\b(ga|gak|nggak|enggak|tidak) ?(tau|tahu|yakin)\b|terserah|bebas aja|umum aja"


def _first(patterns, text):
    for pattern, value in patterns:
        if re.search(pattern, text):
            return value
    return None


def _all(patterns, text):
    return [value for pattern, value in patterns if re.search(pattern, text)]


def quick_extract(message: str, profile: Profile) -> Extraction | None:
    text = message.lower()
    if re.search(SHOP, text):
        return None

    face = _first(FACE, text) if re.search(r"wajah|muka|face|bentuk", text) else None
    texture = _first(TEXTURE, text)
    thickness = _first(THICKNESS, text) if re.search(r"rambut|tebal|tipis|lebat", text) else None
    undertone = _first(UNDERTONE, text)
    if re.search(VIRGIN, text):
        condition = ["virgin"]
    else:
        condition = _all(CONDITION, text)
    issues = _all(ISSUES, text)

    intent = next((name for name, pattern in INTENTS if re.search(pattern, text)), None)
    if intent is None:
       
        if face or texture or thickness:
            intent = "hairstyle"
        elif undertone or condition:
            intent = "hair_color"
        elif issues:
            intent = "treatment"
        else:
            return None  

    merged = describe(profile)
    query_bits = [message]
    if merged != "(belum ada data profil)":
        query_bits.append(merged)
    return Extraction(
        intent=intent, face_shape=face, hair_texture=texture, hair_thickness=thickness,
        undertone=undertone, hair_condition=condition, issues=issues,
        wants_general_answer=bool(re.search(GENERAL, text)),
        search_query=" ; ".join(query_bits),
    )
