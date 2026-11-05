"""User profile ("slots") that drives personalised retrieval.

The browser keeps the profile and sends it with every message, so the server
stays stateless (easy to deploy). Each turn the LLM extracts new slot values
from the latest message and we merge them into the existing profile.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

FaceShape = Literal["oval", "round", "square", "oblong", "heart", "diamond", "triangle"]
HairTexture = Literal["straight", "wavy", "curly"]
Thickness = Literal["thin", "medium", "thick"]
Undertone = Literal["warm", "cool", "neutral"]
Condition = Literal["virgin", "colored", "bleached", "damaged", "chemically_treated", "gray"]
Issue = Literal["dandruff", "hair_fall", "dry", "frizzy", "oily", "thin", "flat",
                "side_puff", "unmanageable_curls", "post_color", "beard", "general"]
Intent = Literal["hairstyle", "hair_color", "treatment", "product", "service",
                 "faq", "greeting", "general"]


class Profile(BaseModel):
    face_shape: Optional[FaceShape] = None
    hair_texture: Optional[HairTexture] = None
    hair_thickness: Optional[Thickness] = None
    undertone: Optional[Undertone] = None
    hair_condition: list[Condition] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)


class Extraction(BaseModel):
    """Structured output requested from the LLM for each user message."""
    intent: Intent
    face_shape: Optional[FaceShape] = None
    hair_texture: Optional[HairTexture] = None
    hair_thickness: Optional[Thickness] = None
    undertone: Optional[Undertone] = None
    hair_condition: list[Condition] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    wants_general_answer: bool = False
    wants_alternatives: bool = False
    on_topic: bool = True
    search_query: str = ""


# Which slots must be known before we can give a personalised answer.
REQUIRED_SLOTS: dict[str, list[str]] = {
    "hairstyle": ["face_shape", "hair_texture"],
    "hair_color": ["undertone", "hair_condition"],
    "treatment": ["issues"],
}

LABELS_ID = {
    "face_shape": "bentuk wajah", "hair_texture": "tekstur rambut", "hair_thickness": "ketebalan rambut",
    "undertone": "undertone kulit", "hair_condition": "kondisi/riwayat rambut", "issues": "masalah rambut",
    "oval": "oval", "round": "bulat", "square": "kotak", "oblong": "lonjong", "heart": "hati",
    "diamond": "diamond", "triangle": "segitiga", "straight": "lurus", "wavy": "bergelombang",
    "curly": "keriting", "thin": "tipis", "medium": "sedang", "thick": "tebal", "warm": "warm",
    "cool": "cool", "neutral": "neutral", "virgin": "virgin hair", "colored": "pernah dicat",
    "bleached": "pernah di-bleaching", "damaged": "rusak/kering", "chemically_treated":
    "pernah smoothing/rebonding/perm", "gray": "beruban",
}


def merge(profile: Profile, ext: Extraction) -> Profile:
    data = profile.model_dump()
    for field in ("face_shape", "hair_texture", "hair_thickness", "undertone"):
        value = getattr(ext, field)
        if value:
            data[field] = value
    for field in ("hair_condition", "issues"):
        new_values = getattr(ext, field)
        if new_values:
            merged = list(dict.fromkeys(data[field] + new_values))
            # "virgin" contradicts any processing history
            if field == "hair_condition" and any(v != "virgin" for v in new_values):
                merged = [v for v in merged if v != "virgin"]
            if field == "hair_condition" and new_values == ["virgin"]:
                merged = ["virgin"]
            data[field] = merged
    return Profile(**data)


def missing_slots(intent: str, profile: Profile) -> list[str]:
    missing = []
    for slot in REQUIRED_SLOTS.get(intent, []):
        value = getattr(profile, slot)
        if not value:
            missing.append(slot)
    return missing


def describe(profile: Profile) -> str:
    parts = []
    for field, value in profile.model_dump().items():
        if not value:
            continue
        if isinstance(value, list):
            value = ", ".join(LABELS_ID.get(v, v) for v in value)
        else:
            value = LABELS_ID.get(value, value)
        parts.append(f"{LABELS_ID[field]}: {value}")
    return "; ".join(parts) if parts else "(belum ada data profil)"
