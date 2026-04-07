# Dockerfile for Coqui TTS Local Server
FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

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

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN python3.12 -m venv venv && \
    ./venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create assets structure
RUN mkdir -p assets/models assets/cache assets/voices/standard assets/voices/elite

# Entrypoint
RUN chmod +x entrypoint.sh

# Expose port
EXPOSE 5100

ENTRYPOINT ["./entrypoint.sh"]
