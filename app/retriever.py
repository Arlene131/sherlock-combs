"""Retrieval with metadata filtering.

For each intent we run a small "retrieval plan": several sub-queries, each limited
to certain categories and filtered by the user's profile (e.g. face_round=True).
If a filtered sub-query finds too little, its filters are relaxed one by one.
On top of that, one unfiltered semantic query catches anything the plan missed.
"""
from app.config import settings
from app.embeddings import get_embedder
from app.profile import Profile
from app.vector_store import FAQ, KNOWLEDGE, query

# intent -> list of (categories, profile filters to apply, k)
PLANS: dict[str, list[tuple[list[str], list[str], int]]] = {
    "hairstyle": [
        (["face_guide"], ["face"], 1),
        (["hairstyle"], ["face", "texture", "thickness"], 4),
        (["hair_type_guide"], [], 1),
    ],
    "hair_color": [
        (["color_guide"], ["undertone"], 1),
        (["hair_color"], ["undertone"], 4),
        (["hair_condition"], ["condition"], 2),
    ],
    "treatment": [
        (["treatment"], ["issue"], 3),
        (["hair_condition"], ["condition"], 1),
    ],
    "product": [(["product", "product_guide"], [], 4)],
    "service": [(["service"], [], 4)],
}

# Guides used when the bot must ask the user for missing information.
GUIDE_FOR_SLOT = {
    "face_shape": "FS-identify",
    "hair_texture": "HT-guide",
    "undertone": "UT-guide",
    "hair_condition": "CD-identify",
}


def _flag_filters(name: str, profile: Profile) -> list[dict]:
    """Translate a profile field into Chroma 'where' clauses."""
    if name == "face" and profile.face_shape:
        return [{f"face_{profile.face_shape}": True}]
    if name == "texture" and profile.hair_texture:
        return [{f"tex_{profile.hair_texture}": True}]
    if name == "thickness" and profile.hair_thickness:
        return [{f"thick_{profile.hair_thickness}": True}]
    if name == "undertone" and profile.undertone:
        return [{f"ut_{profile.undertone}": True}]
    if name == "condition" and profile.hair_condition:
        opts = [{f"cond_{c}": True} for c in profile.hair_condition]
        return [opts[0] if len(opts) == 1 else {"$or": opts}]
    if name == "issue" and profile.issues:
        opts = [{f"issue_{i}": True} for i in profile.issues]
        return [opts[0] if len(opts) == 1 else {"$or": opts}]
    return []


def _where(categories: list[str] | None, clauses: list[dict]) -> dict | None:
    parts = []
    if categories:
        parts.append({"category": categories[0]} if len(categories) == 1 else {"category": {"$in": categories}})
    parts.extend(clauses)
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else {"$and": parts}


# Guide chunks are background context; they may be repeated even when the user asks for alternatives.
GUIDE_CATEGORIES = {"face_guide", "hair_type_guide", "color_guide", "undertone_guide", "product_guide"}


def _filtered_search(vector, categories, filter_names, k, profile, exclude=frozenset()) -> list[dict]:
    clauses_per_filter = [_flag_filters(n, profile) for n in filter_names]
    # Relax filters from the last (least important) to the first.
    for keep in range(len(clauses_per_filter), -1, -1):
        clauses = [c for group in clauses_per_filter[:keep] for c in group]
        hits = query(KNOWLEDGE, vector, k + len(exclude), _where(categories, clauses))
        hits = [h for h in hits if h["id"] not in exclude][:k]
        if len(hits) >= min(k, 2) or keep == 0:
            for h in hits:
                h["filters"] = [n for n in filter_names[:keep] if _flag_filters(n, profile)]
            return hits
    return []


def retrieve(search_query: str, intent: str, profile: Profile,
             exclude: set[str] | None = None, alternatives: bool = False) -> list[dict]:
    """exclude: chunk ids already shown earlier; skipped (except guides) when the user asks for alternatives."""
    vector = get_embedder().embed_query(search_query)
    results: dict[str, dict] = {}
    skip = frozenset(exclude or ()) if alternatives else frozenset()

    for categories, filter_names, k in PLANS.get(intent, []):
        is_guide = bool(categories) and set(categories) <= GUIDE_CATEGORIES
        for hit in _filtered_search(vector, categories, filter_names, k, profile,
                                    frozenset() if is_guide else skip):
            results.setdefault(hit["id"], hit)

    # Unfiltered semantic search as a safety net.
    for hit in query(KNOWLEDGE, vector, settings.rag_top_k + len(skip)):
        if hit["score"] >= settings.rag_min_score and hit["id"] not in skip:
            results.setdefault(hit["id"], hit)

    return sorted(results.values(), key=lambda h: h["score"], reverse=True)


def get_guides(slots: list[str]) -> list[dict]:
    from app.vector_store import get_collection

    ids = [GUIDE_FOR_SLOT[s] for s in slots if s in GUIDE_FOR_SLOT]
    if not ids:
        return []
    res = get_collection(KNOWLEDGE).get(ids=ids, include=["documents", "metadatas"])
    return [
        {"id": i, "text": d, "metadata": m, "score": 1.0}
        for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
    ]


def match_faq(question: str) -> dict | None:
    """Return the FAQ answer if the question is (almost) identical to a known FAQ."""
    vector = get_embedder().embed_query(question)
    hits = query(FAQ, vector, 1)
    if hits and hits[0]["score"] >= settings.faq_min_score:
        hit = hits[0]
        return {"faq_id": hit["metadata"]["faq_id"], "answer": hit["metadata"]["answer"],
                "matched_question": hit["text"], "score": hit["score"]}
    return None
