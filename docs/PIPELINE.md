# Sherlock Combs Chatbot — RAG Pipeline

A retrieval-augmented chatbot for a (fictional) men's barbershop. It recommends
haircuts by face shape and hair type, hair colours by skin undertone and hair
condition, and treatments by hair problem — and only ever recommends services and
products that exist in the shop's catalog.

## 1. Stack at a glance

| Layer | Choice | Why |
|---|---|---|
| Orchestration | Hand-written Python (no LangChain) | Every step is visible and explainable |
| Embedding | `gemini-embedding-001` (768-d) via API; optional local `multilingual-e5-small` | Multilingual, no model on the server, fits free hosting |
| Vector DB | ChromaDB (persistent, cosine) | Real vector index + metadata filtering |
| LLM | Google Gemini Flash-Lite (free tier) via `google-genai` | Fast, larger free quota than Flash |
| Backend | FastAPI | Simple JSON API, also serves the UI |
| Frontend | Plain HTML/CSS/JS | No build step, one deployable app |
| Face shape | MediaPipe Face Landmarker in the browser | Camera frames never leave the device |
| Hosting | Render free web service | Free, public HTTPS link (HF Docker Spaces became paid) |

## 2. Data (knowledge base)

```
data/
├── catalog.json            # 20 services + 13 products  ← single source of truth
├── faq.json                # 11 FAQs, each with several question phrasings
└── knowledge/
    ├── hairstyles.json     # face-shape guides + 18 hairstyles (face × texture × thickness)
    ├── hair_colors.json    # undertone guides + 12 colour options (undertone × bleach need)
    ├── hair_conditions.json# virgin / colored / bleached / damaged / chemical / henna / gray + safety
    └── treatments.json     # problem → service/product (dandruff, hair fall, dry, side puff, ...)
```

Content was summarised and rewritten in Indonesian from public grooming and
colourist guides. Every entry links to catalog IDs (`service_ids`, `product_ids`),
and ingestion fails if an entry references an ID that is not in the catalog.

## 3. Offline pipeline — ingestion (`python -m app.ingest`)

```
JSON entries ──► chunking ──► metadata ──► embedding ──► ChromaDB
```

- **Chunking: 1 entry = 1 chunk.** Entries are small, self-contained facts
  (one hairstyle, one colour). Fixed 700-character chunking would cut
  "style X suits face Y" in half; entry-based chunking never does.
  Catalog items are also added as chunks so product/service questions work.
- **Metadata:** list fields become boolean flags, e.g.
  `face_shapes: ["round","oval"]` → `face_round=True, face_oval=True`
  (Chroma metadata must be scalar). Plus `category`, `title`, linked IDs.
- **Embedding:** asymmetric retrieval — documents use task type `RETRIEVAL_DOCUMENT`,
  questions `RETRIEVAL_QUERY` (with local E5: prefixes `passage: ` / `query: `).
  Vectors are L2-normalised, so cosine similarity = dot product. The collection stores
  which embedding model built it; on start-up the index is rebuilt if that changed.
- **Store:** two collections — `knowledge` (96 chunks) and `faq`
  (every question phrasing → fixed answer). Re-running ingest rebuilds them,
  so there are never duplicates.

## 4. Online pipeline — answering a message (`app/chat_service.py`)

```
user message + history + profile (sent by the browser)
   │
   ├─1. FAQ check ── similarity ≥ FAQ_MIN_SCORE? ──► fixed answer (no LLM call)
   │
   ├─2. Profiling ── Gemini structured output → intent + slots
   │                 (face_shape, hair_texture, thickness, undertone, hair_condition, issues)
   │                 merged into the existing profile
   │
   ├─3. Slot check ── required slots missing? ──► ask the user, using guide chunks
   │                   hairstyle  → face_shape + hair_texture
   │                   hair_color → undertone + hair_condition
   │                   treatment  → issues
   │                   (skipped if the user explicitly wants a general answer)
   │
   ├─4. Retrieval ── per-intent plan of filtered sub-queries in ChromaDB
   │                 e.g. hairstyle: face guide (face filter) + 4 hairstyles
   │                 (face + texture + thickness filters, relaxed if too few hits)
   │                 + one unfiltered semantic search (score ≥ RAG_MIN_SCORE)
   │
   ├─5. Generation ── Gemini gets: rules + FULL catalog + retrieved chunks + profile + history
   │                  returns JSON {answer, recommended_ids}
   │
   └─6. Guardrail ── recommended_ids not in catalog are dropped;
                     names and prices on the cards come from catalog.json, not from the LLM
```

The server is **stateless**: the browser stores the conversation and profile and
sends them every turn. This keeps deployment simple (no database server).

LLM calls per message: 0 (FAQ hit) or 2 (profiling + answer/ask).

Latency measures:
- Profiling uses a smaller model (`GEMINI_FAST_MODEL`, Flash-Lite).
- Model "thinking" is set to minimal (`thinking_level` on Gemini 3.x, `thinking_budget=0` on 2.5).
- The embedding model is loaded at server start, not on the first message.
- The answer is streamed (`POST /api/chat/stream`, NDJSON events: `status`, `profile`,
  `delta`, `done`). The trailing `REKOMENDASI: S01, P03` line the LLM writes is held back
  from the stream and parsed into catalog cards.
- Every response reports per-stage timings (`debug.timings_s`), shown under "Sumber jawaban".

## 5. Camera face-shape detection (`static/face.js`)

1. Browser asks for camera permission (only when the user clicks the button).
2. MediaPipe Face Landmarker finds 478 landmarks per frame, continuously (live).
   Frames where the head is turned or tilted are rejected (nose-to-cheek symmetry, eye-line angle).
3. Measurements on the 36-point face-oval contour: cheekbone width, forehead width,
   jaw width, jaw-corner angle. The mesh stops below the hairline, so face length is
   estimated with the facial-thirds rule: length ≈ 1.5 × (brow → chin).
4. A rolling window of the last 20 valid frames is averaged and classified with ratio
   rules → oval, round, square, oblong, heart, diamond, triangle. The window resets when
   no face is visible, so another person can be measured without reloading.
5. The result is shown as an estimate; on confirm it becomes a chat message
   ("bentuk wajahku bulat") and the `face_shape` slot — so the RAG pipeline stays
   identical whether the user typed it or used the camera.

The thresholds are heuristics and should be tuned with real test faces (the raw
measurements are logged to the browser console).

## 6. Comparison with the reference `rag_pdf` project

| rag_pdf (reference) | Sherlock Combs |
|---|---|
| PDF, fixed 700-char chunks with overlap | Curated JSON, 1 entry = 1 chunk |
| Vectors as JSON in MySQL, cosine in Python over all rows | ChromaDB vector index |
| No metadata | Boolean metadata flags + filtered retrieval with relaxation |
| `faqs` table never populated | FAQ collection with phrasings, answered without LLM |
| No conversation memory | History + persistent user profile (slots) |
| Answers anything in the documents | Must ask for missing info; recommendations grounded in catalog |
| Ollama local LLM | Gemini Flash API (deployable) |

## 7. Evaluation

- `pytest` — unit tests for catalog guardrail, profile merging, metadata filters,
  and the chat flow with a mocked LLM (runs offline).
- `python scripts/eval_retrieval.py` — 16 labelled questions, reports retrieval
  hit rate and recall, plus FAQ threshold sanity checks. Use it when tuning
  `RAG_MIN_SCORE`, `FAQ_MIN_SCORE`, or editing the knowledge base.

## 8. Tuning knobs (`.env`)

| Variable | Default | Effect |
|---|---|---|
| `RAG_TOP_K` | 4 | Size of the unfiltered safety-net search |
| `RAG_MIN_SCORE` | 0.75 | Minimum similarity for safety-net hits (E5 scores are compressed, ~0.7–0.9) |
| `FAQ_MIN_SCORE` | 0.90 | Higher = FAQ shortcut only for near-identical questions |
| `HISTORY_TURNS` | 6 | Messages of history given to the LLM |
| `LLM_TEMPERATURE` | 0.4 | Creativity of answers (profiling always uses 0) |

## 9. Security guardrails (`app/guard.py`)

Defence in depth, structured like Guardrails AI (Guard → validators → on_fail), implemented without
the `guardrails-ai` package because it adds ~240 MB (over Vercel's 500 MB limit) and conflicts with
`google-genai` on `tenacity`.

| Layer | Where | What it stops |
|---|---|---|
| 1. Input rules | before any LLM call | injection phrases (ID/EN), fake role tags, encoded payloads, non-consultation tasks (code, poems, recipes, school work, politics), > 500 chars |
| 2. Untrusted history | before prompting | forged assistant/system turns sent by the browser |
| 3. Topic gate | after profiling | off-topic intents (LLM `on_topic` flag + domain allow-list) |
| 4. Prompt design | prompts.py | user text wrapped in `<pesan_pengguna>` and declared as data; `<`/`>` neutralised |
| 5. Output rules | while generating | prompt leaks, code |
| 6. LLM judge (`RestrictToTopic`) | risky inputs + every answer | disguised tasks, e.g. "format this recipe for the barbershop waiting room" |

Answers are generated in full and validated **before** anything reaches the UI; the judge fails
closed. A per-client rate limit (15 messages/minute) protects the API quota.
`tests/test_security.py` holds the red-team cases.
