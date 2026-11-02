"""Loads the knowledge base and turns each entry into one chunk + metadata.

Chunking strategy: 1 entry = 1 chunk. Each entry is already a small, self-contained
piece of knowledge (e.g. one hairstyle, one hair colour), so we never cut a
recommendation in half the way fixed-size character chunking would.

Metadata: list fields (face_shapes, undertones, ...) are flattened into boolean
flags such as face_round=True, because ChromaDB metadata values must be scalars.
These flags power metadata filtering at query time.
"""
import json

from app.catalog import items_by_id, load_catalog
from app.config import settings

# list field in JSON -> metadata flag prefix
FLAG_FIELDS = {
    "face_shapes": "face",
    "hair_textures": "tex",
    "hair_thickness": "thick",
    "undertones": "ut",
    "conditions": "cond",
    "issues": "issue",
}


def _chunk_text(entry: dict) -> str:
    """Text that gets embedded and later shown to the LLM."""
    return f"{entry['title']}\n{entry['content']}"


def _metadata(entry: dict) -> dict:
    meta = {
        "category": entry["category"],
        "title": entry["title"],
        "service_ids": ",".join(entry.get("service_ids", [])),
        "product_ids": ",".join(entry.get("product_ids", [])),
    }
    for field, prefix in FLAG_FIELDS.items():
        for value in entry.get(field, []):
            meta[f"{prefix}_{value}"] = True
    return meta


def _catalog_entries() -> list[dict]:
    """Each service/product also becomes a chunk, so questions like
    'apa bedanya pomade oil based dan water based?' can be retrieved."""
    entries = []
    cat = load_catalog()
    for s in cat["services"]:
        entries.append({
            "id": s["id"], "category": "service", "title": f"Jasa: {s['name']}",
            "content": f"{s['description']} Harga {s['price']} rupiah, durasi sekitar {s['duration_min']} menit.",
            "service_ids": [s["id"]], "product_ids": [],
        })
    for p in cat["products"]:
        entries.append({
            "id": p["id"], "category": "product", "title": f"Produk: {p['name']}",
            "content": f"{p['description']} Harga {p['price']} rupiah.",
            "service_ids": [], "product_ids": [p["id"]],
        })
    return entries


def load_knowledge_entries() -> list[dict]:
    entries = []
    for path in sorted(settings.knowledge_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            entries.extend(json.load(f))
    entries.extend(_catalog_entries())
    validate_entries(entries)
    return entries


def validate_entries(entries: list[dict]) -> None:
    """Fail fast if the knowledge base references an item that is not in the catalog."""
    known = items_by_id()
    ids_seen = set()
    for e in entries:
        if e["id"] in ids_seen:
            raise ValueError(f"Duplicate knowledge id: {e['id']}")
        ids_seen.add(e["id"])
        for ref in e.get("service_ids", []) + e.get("product_ids", []):
            if ref not in known:
                raise ValueError(f"{e['id']} references unknown catalog item {ref}")


def to_documents(entries: list[dict]) -> tuple[list[str], list[str], list[dict]]:
    ids = [e["id"] for e in entries]
    texts = [_chunk_text(e) for e in entries]
    metas = [_metadata(e) for e in entries]
    return ids, texts, metas


def load_faq() -> list[dict]:
    with open(settings.faq_path, encoding="utf-8") as f:
        return json.load(f)
