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

- **Hybrid Concurrency:** 
  - **Hot Worker:** Keeps the primary model resident in VRAM for sub-second (XTTSv2 ~1.0s) inference.
  - **Cold Workers:** Spawns on-demand subprocesses on GPU when the main lane is busy, ensuring true parallel synthesis without GIL blocking.
- **OpenAI Compatible:** Native support for OpenAI parameters (`model`, `voice`, `speed`, `response_format`).
- **Multilingual Excellence:** Native support for 16+ languages with dynamic language switching via the `language` parameter.
- **Stark Elite Gallery:** Pre-mapped identities for assistant, voice-b, a character, and more.
- **Multi-Format Output:** Real-time conversion to `mp3`, `opus`, `flac`, or `wav` via FFmpeg.
- **Intelligent Caching:** MD5-based caching of audio results to ensure zero-latency for repeated requests.

## 📦 Installation & Setup

We use a modular setup process. The primary `setup.sh` orchestrates the environment, while `setup_assets.sh` handles infrastructure.

### 1. Unified Installation
```bash
git clone https://github.com/fakehec/coqui-tts-local-server.git
cd coqui-tts-local-server
chmod +x setup.sh
./setup.sh
```

### 2. Manual Vocal Provisioning (Mandatory)
Due to copyright and licensing, reference voice files (.wav) are **not provided**. You must provide your own samples:
- **Standard Voices**: Place samples in `/opt/ai/assets/voices/standard/` (e.g., `alloy.wav`, `echo.wav`).
- **Elite Voices**: Place samples in `/opt/ai/assets/voices/elite/` (e.g., `redacted-voice.wav`, `redacted-voice.wav`).

Refer to [CLONE_VOICES.md](./CLONE_VOICES.md) for instructions on creating high-quality reference files.

## 🛠 Execution

### Manual Execution (Console)
```bash
source venv/bin/activate
# Startup with default XTTSv2
uvicorn main_tts:app --host 0.0.0.0 --port 5100

# Startup with a specific pre-loaded model
python main_tts.py --model tts_models/en/ljspeech/vits
```

### 🚀 Model Architecture & Performance

To ensure sub-second latency, this server uses a **Hot Worker** model. The primary TTS model is pre-loaded into VRAM during startup.

*   **Default Behavior**: Defaults to `tts_models/multilingual/multi-dataset/xtts_v2`.
*   **Startup Override**: Use the `--model` flag to pre-load a different architecture.
*   **API Compliance Note**: The `model` parameter in API requests is currently ignored for performance reasons (always uses the pre-loaded Hot Worker).

### 📦 Recommended Models Gallery

| Model Name | Primary Use Case |
| :--- | :--- |
| **XTTS v2** | Professional Cloning (16 languages) - Default |
| **VITS (LJSpeech)** | Ultra-fast English (Female) |
| **VITS (VCTK)** | 100+ Pre-set English Voices |
| **VITS (CSS10)** | High-speed Native Spanish |
| **YourTTS** | Legacy Multilingual Cloning |

### 3. System Service (systemd)
1. Create: `/etc/systemd/system/coqui-tts.service`
2. Configuration:

```ini
[Unit]
Description=Coqui TTS Local Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/usr/local/lib/coqui
Environment="TTS_HOME=/opt/ai/models/speech/coqui-tts"
Environment="VOICE_ASSET_DIR=/opt/ai/assets/voices"
# Example starting with XTTSv2
ExecStart=/usr/local/lib/coqui/venv/bin/python main_tts.py --model tts_models/multilingual/multi-dataset/xtts_v2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

3. Start: `sudo systemctl enable --now coqui-tts`

## 🔍 Debugging & Monitoring

Set `DEBUG=true` to enable worker routing traces:
`DEBUG=true python main_tts.py`

## 📊 Performance (Uttera Metrics)

| Task | Latency (Hot Lane) | Latency (Cold Lane) |
| :--- | :--- | :--- |
| Short Response (XTTSv2) | **~1.0s** | ~19s (Cold load) |
| VITS Inference | **<0.5s** | ~4s (Cold load) |
| Cached Response | **<0.02s** | <0.02s |

## 🛡 License

GNU GPL v3. 
Maintainers: Hugo L. Espuny & Uttera
