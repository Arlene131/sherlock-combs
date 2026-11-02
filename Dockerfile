FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 CHROMA_DIR=/app/chroma_db PORT=8000
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
