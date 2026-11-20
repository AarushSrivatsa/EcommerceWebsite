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
# ffmpeg renders video; Mesa/EGL and fontconfig are required by skia-python at runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    ffmpeg \
    libegl1 \
    libegl-mesa0 \
    libgl1 \
    libglx0 \
    libglx-mesa0 \
    libgl1-mesa-dri \
    libglvnd0 \
    libfontconfig1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    MALLOC_ARENA_MAX=2

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -c "import skia; print('Skia runtime dependencies OK')"

# Cache both models in the image so Render does not download them on first use.
ENV HF_HOME=/models/huggingface \
    PHONON_MODEL_PATH=hf://gradium/phonon-31m-en \
    PHONON_QUANT=q8 \
    FASTEMBED_CACHE_PATH=/models/fastembed
RUN python -c "import ptts; ptts.TTS('hf://gradium/phonon-31m-en', lang='en', quant='q8')" \
 && python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY . .
COPY --from=site /site/dist frontend/dist

# One API worker keeps model memory and in-process job coordination bounded on 512 MB.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
