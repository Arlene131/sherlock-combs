import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.profile import Profile  # noqa: E402
from app.retriever import match_faq, retrieve  # noqa: E402


def main() -> None:
    cases = json.loads((ROOT / "eval" / "retrieval_questions.json").read_text(encoding="utf-8"))
    hits, found_total, expected_total = 0, 0, 0
    for case in cases:
        results = retrieve(case["question"], case["intent"], Profile(**case["profile"]))
        got = [r["id"] for r in results]
        found = [e for e in case["expected"] if e in got]
        hits += bool(found)
        found_total += len(found)
        expected_total += len(case["expected"])
        mark = "OK " if found else "MISS"
        print(f"[{mark}] {case['question']}")
        print(f"       expected found {len(found)}/{len(case['expected'])} | top: {got[:5]}")
    print("-" * 70)
    print(f"Hit rate: {hits}/{len(cases)} = {hits / len(cases):.0%}")
    print(f"Recall  : {found_total}/{expected_total} = {found_total / expected_total:.0%}")

    print("\nFAQ shortcut check (should match / should NOT match):")
    for q, should in [("jam berapa buka?", True), ("bisa bayar qris?", True),
                      ("muka bulat cocok potong apa?", False), ("rambut rontok kenapa ya", False)]:
        m = match_faq(q)
        status = "OK " if bool(m) == should else "FIX"
        print(f"  [{status}] {q!r} -> {m['faq_id'] + ' (' + str(m['score']) + ')' if m else 'no FAQ'}")


if __name__ == "__main__":
    main()
