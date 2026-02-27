# coqui-tts-local-server

High-performance Coqui TTS API server with a hybrid "Hot/Cold" worker architecture. 

**Ideal for locally running installations of agents like OpenClaw or Open-WebUI, where the media should not leave the private local domain.**

## 🚀 Key Features

- **Hybrid Concurrency:**
  - **Hot Worker:** Keeps an XTTSv2 model resident in VRAM for fast inference.
  - **Cold Workers:** Spawns on-demand subprocesses on GPU when the main lane is busy.
- **OpenAI Compatible:** Native support for OpenAI parameters (`model`, `voice`, `speed`, `response_format`).
- **Stark Elite Gallery:** Pre-mapped voices for iconic AIs like assistant, voice-b, a character, and more.
- **Multi-Format Output:** Real-time conversion to `mp3`, `opus`, `flac`, or `wav`.

## 📦 Installation & Setup

To simplify the deployment, we provide a unified provisioning script that installs system dependencies, creates the folder structure, and downloads the recommended models and voices.

### 1. Clone and Install Python Dependencies
```bash
git clone https://github.com/fakehec/coqui-tts-local-server.git
cd coqui-tts-local-server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Provision Assets (Models & Voices)
Run the automated script to set up `espeak-ng`, standard voices (`alloy`, etc.), and the XTTS/VITS models in `/opt/ai/`:

```bash
chmod +x setup_assets.sh
./setup_assets.sh
```

## 🛠 Execution

### Manual Execution (Console)
```bash
# Execute using Uvicorn
uvicorn main_tts:app --host 0.0.0.0 --port 5100
```

### 🚀 Model Architecture & Performance

To ensure sub-second latency, this server uses a **Hot Worker** model. The primary TTS model is pre-loaded into VRAM during startup.

*   **Default Behavior**: Defaults to `tts_models/multilingual/multi-dataset/xtts_v2`.
*   **Startup Override**: Use the `--model` flag: `python main_tts.py --model <model_name>`.
*   **API Compliance Note**: The `model` parameter in API requests is currently ignored for performance reasons.

### 📦 Recommended Models Gallery

| Model Name | Primary Use Case |
| :--- | :--- |
| **XTTS v2** | Professional Cloning (16 languages) |
| **VITS (LJSpeech)** | Ultra-fast English (Female) |
| **VITS (CSS10)** | High-speed Native Spanish |

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
ExecStart=/usr/local/lib/coqui/bin/python -m uvicorn main_tts:app --host 0.0.0.0 --port 5100
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

3. Start: `sudo systemctl enable --now coqui-tts`

## 🔍 Debugging & Monitoring

Set `DEBUG=true` to enable worker routing traces:
`DEBUG=true uvicorn main_tts:app --host 0.0.0.0 --port 5100`

## 📊 Performance (Sphinx GPU)

| Task | Latency (Hot Lane) | Latency (Cold Lane) |
| :--- | :--- | :--- |
| Short Response | **~1.0s** | ~19s (Cold load) |
| Cached Response | **<0.02s** | <0.02s |

## 🛡 License

GNU GPL v3. 
Maintainers: Hugo L. Espuny & Uttera
