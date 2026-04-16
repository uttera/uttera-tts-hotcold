# Dockerfile for uttera-tts-hotcold
#
# Build with backend selection:
#   docker build --build-arg TTS_BACKEND=coqui -t uttera-tts-hotcold:coqui .
#   docker build --build-arg TTS_BACKEND=voxcpm -t uttera-tts-hotcold:voxcpm .
#
FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

ARG TTS_BACKEND=coqui

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TTS_BACKEND=${TTS_BACKEND}

# Install system dependencies (Python 3.12 and FFmpeg 6.x ship with Ubuntu 24.04)
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    ffmpeg \
    curl \
    espeak-ng \
    file \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements files first (Docker layer caching)
COPY requirements.txt requirements-*.txt ./

# Install backend-specific dependencies
RUN python3.12 -m venv venv && \
    ./venv/bin/pip install --no-cache-dir -r requirements-${TTS_BACKEND}.txt

# Copy application code
COPY . .

# Create assets structure
RUN mkdir -p assets/models assets/cache assets/voices/standard assets/voices/elite

# Entrypoint
RUN chmod +x entrypoint.sh

EXPOSE 5100

ENTRYPOINT ["./entrypoint.sh"]
