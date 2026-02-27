# coqui-tts-local-server

High-performance Coqui TTS API server with a hybrid "Hot/Cold" worker architecture. 

**Ideal for locally running installations of agents like OpenClaw or Open-WebUI, where the media should not leave the private local domain.**

## 🚀 Key Features

- **Hybrid Concurrency:** Hot Worker for speed, Cold Workers for parallel synthesis.
- **OpenAI Compatible:** Support for parameters like `model`, `voice`, `speed`, and `response_format`.
- **Stark Elite Gallery:** Mapped voices for assistant, voice-b, a character, and more.
- **Multi-Format Output:** Real-time conversion to `mp3`, `opus`, `flac`, or `wav`.

## 📦 Installation & Setup

We use a modular setup process. The primary `setup.sh` orchestrates the environment, while `setup_assets.sh` handles infrastructure.

### 1. Unified Installation
```bash
git clone https://github.com/fakehec/coqui-tts-local-server.git
cd coqui-tts-local-server

# This script creates the venv, installs dependencies, and provisions assets
chmod +x setup.sh
./setup.sh
```

### 2. Manual Vocal Provisioning (Mandatory)
Due to copyright regulations, reference voice files (.wav) are **not included**. You must provide your own samples in the following directory:

- Place reference voices in: `/opt/ai/assets/voices/`
- Example: `/opt/ai/assets/voices/standard/alloy.wav`

Refer to [CLONE_VOICES.md](./CLONE_VOICES.md) for instructions on creating high-quality reference files.

## 🛠 Execution

### Manual Execution (Console)
```bash
source venv/bin/activate
uvicorn main_tts:app --host 0.0.0.0 --port 5100
```

### 🚀 Model Architecture & Performance
... [rest of the sections remain unchanged] ...
