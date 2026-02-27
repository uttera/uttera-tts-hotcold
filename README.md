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
- **Intelligent Caching:** MD5-based caching for zero-latency repeated requests.

## 📦 Installation & Setup

### 1. Unified Installation
```bash
git clone https://github.com/fakehec/coqui-tts-local-server.git
cd coqui-tts-local-server
chmod +x setup.sh
./setup.sh
```

### 2. Vocal Provisioning
- **Standard Voices**: The server automatically provisions the 6 standard OpenAI identities (Alloy, Echo, Fable, Onyx, Nova, Shimmer) during setup.
- **Elite/Custom Voices**: Reference voice files (.wav) for custom cloning are **not provided** due to copyright. Place your samples in `/opt/ai/assets/voices/elite/`.
- Refer to [CLONE_VOICES.md](./CLONE_VOICES.md) for instructions on creating high-quality reference files.

## 🛠 Execution

The server uses direct **Uvicorn** execution for maximum ASGI performance.

### Manual Execution (Console)
```bash
source venv/bin/activate

# Localhost only (Default: 127.0.0.1:5100)
uvicorn main_tts:app --host 127.0.0.1 --port 5100

# Expose to Local Network (0.0.0.0)
uvicorn main_tts:app --host 0.0.0.0 --port 5100
```

### ⚙️ Environment Variables
- `TTS_MODEL`: Model name to pre-load into the Hot Worker (default: `xtts_v2`).
- `DEBUG`: Set to `true` to enable worker routing traces.

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
Environment="TTS_MODEL=tts_models/multilingual/multi-dataset/xtts_v2"
ExecStart=/usr/local/lib/coqui/venv/bin/uvicorn main_tts:app --host 127.0.0.1 --port 5100
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 🔒 Security & Network Note
By default, the server binds to **`127.0.0.1`** on port **`5100`**. 
- To allow external network access, modify the `--host` parameter to `0.0.0.0` in the execution command or systemd unit.
- **WARNING**: This API **does not have authentication**. Exposing it to the network via `0.0.0.0` represents a security risk. Ensure the server is protected by a firewall or operating within a secure VPN/Local Network.

## 📊 Performance (Uttera Metrics)
| Task | Latency (Hot Lane) | Latency (Cold Lane) |
| :--- | :--- | :--- |
| Short Response (XTTSv2) | **~1.0s** | ~19s (Cold load) |
| Cached Response | **<0.02s** | <0.02s |

## 🛡 License
GNU GPL v3. Maintainers: Hugo L. Espuny & Uttera
