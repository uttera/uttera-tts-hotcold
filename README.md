# coqui-tts-local-server

High-performance Coqui TTS API server with a hybrid "Hot/Cold" worker architecture. 

**Ideal for locally running installations of agents like OpenClaw or Open-WebUI, where the media should not leave the private local domain.**

## 🚀 Key Features

- **Hybrid Concurrency:**
  - **Hot Worker:** Keeps an XTTSv2 model resident in VRAM for fast (1.0s) inference.
  - **Cold Workers:** Spawns on-demand subprocesses on GPU when the main lane is busy, ensuring true parallel synthesis.
- **OpenAI Compatible:** Native support for `application/json` and OpenAI parameters (`model`, `voice`, `speed`, `response_format`).
- **Stark Elite Gallery:** Pre-mapped voices for iconic AIs like assistant, voice-b, a character, a voice, a character, and more. *Note: Voice samples are not included due to copyright. Please refer to [CLONE_VOICES.md](./CLONE_VOICES.md) for instructions on how to obtain and install your own reference files.*
- **Multi-Format Output:** Real-time conversion to `mp3`, `opus`, `flac`, or `wav` via FFmpeg.
- **Production-Ready:** Infrastructure-grade orchestrator with hardware lock management and intelligent caching.

## 📦 Requirements

- **Coqui TTS:** This server is built upon the official [Coqui TTS Engine](https://github.com/coqui-ai/TTS).
- **FFmpeg:** Required for real-time audio conversion.
- **NVIDIA GPU:** Mandatory for hardware acceleration (CUDA).
- **Python 3.10+**
- **espeak-ng:** Mandatory for phonemization in many models.

## ⚙️ Setup & Dependencies

It is highly recommended to install the dependencies within a virtual environment.

```bash
# 1. Install system dependency
sudo apt-get update && sudo apt-get install -y espeak-ng

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### 📦 Prerequisites & Model Setup

Before running the server, you must ensure the models are downloaded to the correct path. By default, the server expects models at `/opt/ai/models/speech/coqui-tts`.

```bash
# 1. Create the model directory
sudo mkdir -p /opt/ai/models/speech/coqui-tts
sudo chown -R $USER:$USER /opt/ai/models/speech/

# 2. Configure path
export TTS_HOME="/opt/ai/models/speech/coqui-tts"
```

### 📥 Verified Download Commands

Run these exact commands to provision your local model gallery.

#### 1. XTTS v2 (Uttera Orchestrator)
*Requires a reference voice file to initialize.*
```bash
tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 \
    --text "init" --language_idx "en" \
    --speaker_wav "/opt/ai/assets/voices/standard/alloy.wav" \
    --out_path "/tmp/init.wav"
```

#### 2. VITS - LJSpeech (Ultra-fast English)
```bash
tts --model_name tts_models/en/ljspeech/vits \
    --text "init" --out_path "/tmp/init.wav"
```

#### 3. VITS - VCTK (100+ English Voices)
*Requires a speaker ID to initialize.*
```bash
tts --model_name tts_models/en/vctk/vits \
    --text "init" --speaker_idx "p225" --out_path "/tmp/init.wav"
```

#### 4. VITS - CSS10 (High-speed Native Spanish)
```bash
tts --model_name tts_models/es/css10/vits \
    --text "init" --out_path "/tmp/init.wav"
```

#### 5. YourTTS (Legacy Multilingual)
```bash
tts --model_name tts_models/multilingual/multi-dataset/your_tts \
    --text "init" --language_idx "en" \
    --speaker_wav "/opt/ai/assets/voices/standard/alloy.wav" \
    --out_path "/tmp/init.wav"
```

## 🛠 Installation & Execution

```bash
# Execute using Uvicorn
uvicorn main_tts:app --host 0.0.0.0 --port 5100
```

### 🚀 Model Architecture & Performance

To ensure sub-second latency, this server uses a **Hot Worker** model. The primary TTS model is pre-loaded into VRAM during startup.

*   **Default Behavior**: Defaults to `tts_models/multilingual/multi-dataset/xtts_v2`.
*   **Startup Override**: Use the `--model` flag: `python main_tts.py --model <model_name>`.
*   **API Compliance Note**: The `model` parameter in API requests is currently ignored for performance reasons.

### 2. System Service (systemd)
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

```bash
DEBUG=true uvicorn main_tts:app --host 0.0.0.0 --port 5100
```

## 📊 Performance (Sphinx GPU)

| Task | Latency (Hot Lane) | Latency (Cold Lane) |
| :--- | :--- | :--- |
| Short Response | **~1.0s** | ~19s (Cold load) |
| Cached Response | **<0.02s** | <0.02s |

## 🛡 License

GNU GPL v3. 
Maintainers: Hugo L. Espuny & Uttera
