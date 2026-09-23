# Vero Cloud's AI engine (Phase 13). Not built/pushed anywhere in this phase — this is
# the shape a real deployment would use, reviewed for correctness but not build-verified
# (see docs/ROADMAP.md); actual verification in this phase runs the service directly via
# a local venv, the same way backend/ and ai-engine/ already do.
FROM python:3.11-slim

# OpenCV/FFmpeg need these system libraries to actually decode video, not just import.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /repo

COPY cloud-engine/requirements.txt cloud-engine/requirements.txt
RUN pip install --no-cache-dir -r cloud-engine/requirements.txt

# main.py's sys.path trick expects backend/ as a sibling directory, same as this repo's
# own layout — so this image mirrors that layout under /repo rather than flattening it.
# Only backend/app is needed (not backend/tests, backend/venv, etc.).
COPY backend/app backend/app
COPY cloud-engine/main.py cloud-engine/main.py

WORKDIR /repo/cloud-engine

# No .env is copied in: DATABASE_URL / CAMERA_CREDENTIALS_KEY / AUTH_SECRET_KEY /
# CLOUD_ENGINE_INTERNAL_SECRET come from the real container environment (docker-compose's
# `environment:`, or the deployment platform's own secret store) — never baked into a
# layer.
EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
