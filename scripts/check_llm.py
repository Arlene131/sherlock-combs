import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel  

from app import llm  
from app.config import settings  

THINKING_NAMES = ["thinking_level=" + settings.thinking_level, "thinking_budget=0", "model default"]


class Ping(BaseModel):
    ok: bool


def main() -> None:
    print(f"Answer model : {settings.gemini_model}")
    print(f"Fast model   : {settings.gemini_fast_model}\n")

    for label, model in [("fast model (profiling)", settings.gemini_fast_model),
                         ("answer model", settings.gemini_model)]:
        t = time.perf_counter()
        try:
            llm.generate_json("Reply with ok=true.", "ping", Ping, model=model)
            took = time.perf_counter() - t
            choice = THINKING_NAMES[llm._thinking_choice.get(model, 0)]
            print(f"[OK]   {label:24} {took:5.2f}s  ({choice})")
        except Exception as exc:
            print(f"[FAIL] {label:24} {time.perf_counter() - t:5.2f}s  {exc}")

    t = time.perf_counter()
    try:
        stream = llm.stream_text("Jawab singkat dalam bahasa Indonesia.", "Sebutkan 3 gaya rambut pria.")
        first = next(stream)
        first_at = time.perf_counter() - t
        for _ in stream:
            pass
        print(f"[OK]   streaming answer         first words after {first_at:.2f}s, "
              f"complete after {time.perf_counter() - t:.2f}s")
    except Exception as exc:
        print(f"[FAIL] streaming answer         {exc}")

    print("\nRough guide: under ~2s per step is good. Much slower usually means the model is")
    print("still 'thinking', the free-tier quota is busy (429), or the network is slow.")


if __name__ == "__main__":
    main()
