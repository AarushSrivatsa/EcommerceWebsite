# Stage 1: build the website (Vue) into frontend/dist
FROM node:22-slim AS site
WORKDIR /site
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: the backend, which also serves that website
FROM python:3.12-slim

# ffmpeg builds the section and final videos.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cache both models in the image so Render does not download them on first use.
ENV HF_HOME=/models/huggingface \
    PHONON_MODEL_PATH=hf://gradium/phonon-31m-en \
    PHONON_QUANT=q8 \
    FASTEMBED_CACHE_PATH=/models/fastembed
RUN python -c "import ptts; ptts.TTS('hf://gradium/phonon-31m-en', lang='en', quant='q8')" \
 && python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY . .
COPY --from=site /site/dist frontend/dist

# One worker on purpose: the graph runs and renders are background tasks inside this one process.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
