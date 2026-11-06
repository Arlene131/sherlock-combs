# Sherlock Combs an RAG Barbershop Chatbot

Moshi Dev~

Chatbot for a barbershop. It recommends haircuts, hair colours based on ur(skin undertone × hair condition) and treatments, and only recommends services/products from the shop catalog. Face shape can be typed or estimated with the camera.

How it works: see the [docs/PIPELINE.md](docs/PIPELINE.md).

## Project structure

```
app/            backend (FastAPI) config, catalog, embeddings, vector store,
                ingest, profile, retriever, prompts, llm, chat_service, main
data/           catalog.json, faq.json, knowledge/*.json  (the knowledge base)
static/         web UI index.html, style.css, app.js, face.js (camera)
scripts/        eval_retrieval.py
eval/           labelled retrieval test questions
tests/          offline unit tests (fake embedder + mocked LLM)
docs/           PIPELINE.md
render.yaml     Render deployment (free web service)
Dockerfile      generic container image
```

## Run locally (macOS)

```bash
cd sherlock-combs
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then paste your GEMINI_API_KEY into .env

python -m app.ingest           
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000. The camera works on `localhost` and on HTTPS sites.

Useful checks:

```bash
pytest -q                         
python scripts/eval_retrieval.py   
curl localhost:8000/health
```

`render.yaml` and `Dockerfile` are kept for container hosts (Render, Railway, etc.).

## Notes

- Gemini free tier limits differ per model (check ai.dev/rate-limit). Each chat message uses
  0–2 generation requests and 1–2 embedding requests; Flash-Lite is used because Flash's free daily quota is very small.
- Free-tier prompts may be used by Google to improve its products fine for this     fictional demo, not for real customer data.
- All shop data (name, address, phone, prices) is fictional.

## OTSU!!!
  