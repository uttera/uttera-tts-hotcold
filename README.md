# coqui-tts-local-server

High-performance Coqui TTS API server with a hybrid "Hot/Cold" worker architecture. 

**Ideal for locally running installations of agents like OpenClaw or Open-WebUI, where the media should not leave the private local domain.**

## ⚖️ License & Terms of Service (IMPORTANT)

This server uses **Coqui TTS**, which is released under various licenses depending on the model.
- **XTTS v2** and several other models are released under the **Coqui Public Model License (CPML)**.
- **NON-COMMERCIAL USE ONLY**: Usage is free for personal and non-commercial projects.
- **COMMERCIAL USE**: If you intend to use this for commercial purposes, you **must** purchase a commercial license from Coqui (licensing@coqui.ai).
- By running the installation scripts, you acknowledge and agree to these terms.

## 🚀 Key Features
... [rest of features] ...

## 📦 Installation & Setup

### 1. Unified Installation
```bash
git clone https://github.com/fakehec/coqui-tts-local-server.git
cd coqui-tts-local-server
chmod +x setup.sh
./setup.sh
```

### 2. Manual Vocal Provisioning (Mandatory)
Due to copyright and licensing, reference voice files (.wav) are **not provided**.
- Place your samples in: `/opt/ai/assets/voices/`
- Standard OpenAI voices mapping: `/opt/ai/assets/voices/standard/alloy.wav`, etc.

## 🛠 Execution
... [rest of sections] ...
