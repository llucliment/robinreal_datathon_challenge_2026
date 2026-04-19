FROM python:3.12-slim

WORKDIR /app

# Install CPU-only torch first (~250 MB vs ~2.5 GB for the CUDA wheel).
# uv/pip will see it already satisfies sentence-transformers' torch requirement
# and skip reinstalling the CUDA build.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml ./
RUN pip install --no-cache-dir uv && uv pip install --system .

# Pre-download the sentence-transformers model into the image so the first
# query does not trigger a ~90 MB download at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# App code (copy last to maximise Docker layer cache reuse on rebuilds)
COPY app ./app
COPY apps_sdk ./apps_sdk
COPY README.md ./

# Pre-built database — bootstrap.py detects it and skips the CSV import.
COPY data/listings.db /app/data/listings.db

ENV LISTINGS_DB_PATH=/app/data/listings.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
