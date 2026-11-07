# Stage 1: build the website (Vue) into frontend/dist
FROM node:22-slim AS site
WORKDIR /site
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: the backend, which also serves that website
FROM python:3.12-slim

# ffmpeg builds the videos. (espeak-ng, which Kokoro needs, comes bundled inside the espeakng-loader pip package.)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The models are baked into the image, so a restart or redeploy never downloads them again.
# For a smaller, lighter voice model use KOKORO_MODEL=kokoro-v1.0.int8.onnx
ARG KOKORO_MODEL=kokoro-v1.0.onnx
ADD https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/${KOKORO_MODEL} /models/kokoro.onnx
ADD https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin /models/voices.bin
ENV KOKORO_MODEL_PATH=/models/kokoro.onnx \
    KOKORO_VOICES_PATH=/models/voices.bin \
    FASTEMBED_CACHE_PATH=/models/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-base-en-v1.5')"

COPY . .
COPY --from=site /site/dist frontend/dist

# One worker on purpose: the graph runs and renders are background tasks inside this one process.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
