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
- **Personality Tuning:** Full control over synthesis expressiveness via parameters like `temperature`, `top_p/k`, and `penalties`.
- **Multilingual Excellence:** Native support for 16 languages: `en, es, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, hu, ko, ja` (English by default).
- **Intelligent Caching:** MD5-based caching for zero-latency repeated requests.

## 📦 Installation & Setup

### 1. Prerequisites (Debian/Ubuntu)
Install the following system dependencies first:
```bash
sudo apt update && sudo apt install -y espeak-ng curl file ffmpeg
```

### 2. Unified Installation
```bash
git clone https://github.com/fakehec/coqui-tts-local-server.git
cd coqui-tts-local-server
chmod +x setup.sh
./setup.sh
```

### 3. User Permissions & Hardware Acceleration
To run the server without `sudo` privileges and enable GPU acceleration, the user must belong to the `video` and `render` groups:
```bash
sudo usermod -aG video $USER
sudo usermod -aG render $USER
```
*Note: Restart your session for changes to take effect.*

### 3. Network Permissions
The server listens on port `5100` by default. Ensure the user has permissions to open sockets on this port (standard for ports >1024).

### 4. Vocal Provisioning
- **Standard Voices**: The server automatically provisions the 6 standard OpenAI identities (Alloy, Echo, Fable, Onyx, Nova, Shimmer) during setup.
- **Elite/Custom Voices**: Reference voice files (.wav) for custom cloning are **not provided** due to copyright. Place your samples in `/opt/ai/assets/voices/elite/`.
- Refer to [CLONE_VOICES.md](./CLONE_VOICES.md) for instructions on creating high-quality reference files.

## 🎭 Personality Tuning & Parameters

The server supports advanced personality parameters to tune the output voice. These can be sent via the **API (JSON or Form-data)** or set as system-wide defaults via **environment variables** (or the `.env` file).

| Parameter | Default | Description | Env Variable |
| :--- | :--- | :--- | :--- |
| `temperature` | **0.75** | Higher values increase expressiveness/randomness. | `DEFAULT_TEMPERATURE` |
| `length_penalty`| **1.0** | Controls the length of the generated sequence. | `DEFAULT_LENGTH_PENALTY` |
| `repetition_penalty`| **5.0** | Prevents the model from repeating words/phrases. | `DEFAULT_REPETITION_PENALTY`|
| `top_k` | **50** | Limits sampling to the top K most likely tokens. | `DEFAULT_TOP_K` |
| `top_p` | **0.85** | Nucleus sampling to ensure token diversity. | `DEFAULT_TOP_P` |
| `language` | **en** | Default language code. | `DEFAULT_LANGUAGE` |

### 🌐 Supported Languages
The following language codes are supported: `en, es, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, hu, ko, ja`.

## 🔧 Troubleshooting

### Transformers Compatibility Error
The current version of Coqui-TTS (0.27.5) has a known bug with recent `transformers` versions regarding the `isin_mps_friendly` import. The `setup.sh` script automatically patches this in your virtual environment. If you install manually, ensure you replace that import with `torch.isin`.

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

### ⚙️ Environment Variables & .env

The server includes a `.env.example` file. You can create a **`.env`** file in the root directory to override default behaviors without changing the code.

- `TTS_MODEL`: Model name to pre-load into the Hot Worker (default: `xtts_v2`).
- `DEFAULT_LANGUAGE`: Sets the default language if not specified in the request (default: `en`).
- `DEBUG`: Set to `true` to enable worker routing traces.
- `VENV_PYTHON`: Absolute path to the python executable in the venv (auto-detected if local).

*Note: All personality parameters listed in the section above can also be set via their respective `DEFAULT_*` environment variables.*

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
