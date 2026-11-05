import json
from functools import lru_cache

from app.config import settings


@lru_cache
def load_catalog() -> dict:
    with open(settings.catalog_path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def items_by_id() -> dict[str, dict]:
    cat = load_catalog()
    items = {}
    for s in cat["services"]:
        items[s["id"]] = {**s, "type": "service"}
    for p in cat["products"]:
        items[p["id"]] = {**p, "type": "product"}
    return items


def format_price(value: int) -> str:
    return "Rp" + f"{value:,}".replace(",", ".")


def catalog_as_prompt_text() -> str:
    """Compact catalog listing injected into every LLM prompt (catalog grounding)."""
    lines = ["JASA:"]
    for item in items_by_id().values():
        if item["type"] == "service":
            lines.append(f"- {item['id']} | {item['name']} | {format_price(item['price'])} | {item['description']}")
    lines.append("PRODUK:")
    for item in items_by_id().values():
        if item["type"] == "product":
            lines.append(f"- {item['id']} | {item['name']} | {format_price(item['price'])} | {item['description']}")
    return "\n".join(lines)


def to_cards(ids: list[str]) -> list[dict]:
    """Turn item IDs into UI cards, silently dropping IDs that are not in the catalog."""
    cards, seen = [], set()
    lookup = items_by_id()
    for item_id in ids:
        item_id = (item_id or "").strip().upper()
        if item_id in lookup and item_id not in seen:
            seen.add(item_id)
            item = lookup[item_id]
            cards.append({
                "id": item_id,
                "name": item["name"],
                "type": item["type"],
                "price": item["price"],
                "price_label": format_price(item["price"]),
            })
    return cards
