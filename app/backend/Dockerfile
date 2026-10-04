# ThriftFind backend — production image for Railway / Render (any Docker host).
# Build context is this directory (app/backend).
FROM python:3.12-slim

# Faster, cleaner Python in containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so this layer caches unless requirements change.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code only (data/ is not needed at runtime — seed from your machine against
# the production DATABASE_URL; see DEPLOYMENT.md).
COPY app ./app
COPY run.py .

# Railway/Render inject $PORT. Bind 0.0.0.0 and disable reload for production.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
