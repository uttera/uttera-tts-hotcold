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
  - **Hot Worker:** Primary model resident in VRAM for sub-second (XTTSv2 ~1.0s) inference.
  - **Cold Workers:** Spawns on-demand subprocesses on GPU when the main lane is busy.
- **OpenAI Compatible:** Native support for OpenAI parameters (`model`, `voice`, `speed`, `response_format`).
- **Multilingual Excellence:** Native support for 16+ languages (English by default).
- **Stark Elite Gallery:** Pre-mapped identities for assistant, voice-b, a character, and more.
- **Intelligent Caching:** MD5-based caching for zero-latency repeated requests.

## 📦 Installation & Setup

### 1. Unified Installation
```bash
git clone https://github.com/fakehec/coqui-tts-local-server.git
cd coqui-tts-local-server
chmod +x setup.sh
./setup.sh
```

### 2. Manual Vocal Provisioning (Mandatory)
Due to copyright and licensing, reference voice files (.wav) are **not provided**. You must provide your own samples in `/opt/ai/assets/voices/`. Refer to [CLONE_VOICES.md](./CLONE_VOICES.md).

## 🛠 Execution

The server is unified under the `main_tts.py` entry point.

### Manual Execution (Console)
```bash
source venv/bin/activate

# Localhost only (Default: 127.0.0.1:5100)
python main_tts.py

# Expose to Network (0.0.0.0)
# WARNING: The server has NO AUTHENTICATION. Exposing it to the network is a security risk.
python main_tts.py --host 0.0.0.0 --port 5100 --model tts_models/multilingual/multi-dataset/xtts_v2
```

### ⚙️ Command Line Arguments
- `--host`: Host to bind (default: `127.0.0.1`).
- `--port`: Port to bind (default: `5100`).
- `--model`: Model name to pre-load into the Hot Worker (default: `xtts_v2`).

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
# Example: Exposing to local network on port 5100
ExecStart=/usr/local/lib/coqui/venv/bin/python main_tts.py --host 0.0.0.0 --port 5100
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 🔒 Security Note
By default, the server binds to `127.0.0.1`. If you change this to `0.0.0.0`, the server will be accessible by anyone on your network. Since this API **does not have authentication**, please ensure you are behind a firewall or using a secure VPN.

## 📊 Performance (Uttera Metrics)

| Task | Latency (Hot Lane) | Latency (Cold Lane) |
| :--- | :--- | :--- |
| Short Response (XTTSv2) | **~1.0s** | ~19s (Cold load) |
| Cached Response | **<0.02s** | <0.02s |

## 🛡 License
GNU GPL v3. Maintainers: Hugo L. Espuny & Uttera
