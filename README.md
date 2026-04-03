# coqui-tts-local-server

<p align="center">
  <img src="docs/img/social-preview.png" alt="Coqui TTS Local Server" width="800">
</p>

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
- **GPU Accelerated:** Native support for NVIDIA CUDA via `torch`, ensuring ultra-fast inference and high-quality synthesis.
- **OpenAI Compatible:** Native support for OpenAI parameters (`model`, `voice`, `speed`, `response_format`). Includes `GET /v1/models` for client autodiscovery.
- **Streaming:** `POST /v1/audio/speech/stream` delivers chunked WAV audio in real time via XTTS-v2's `inference_stream()` (Hot Lane only).
- **Personality Tuning:** Full control over synthesis expressiveness via parameters like `temperature`, `top_p/k`, and `penalties`.
- **Multilingual Excellence:** Native support for 16 languages: `en, es, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, hu, ko, ja` (English by default).
- **Intelligent Caching:** MD5-based caching for zero-latency repeated requests. Configurable TTL via `CACHE_TTL_MINUTES`.
- **Health Endpoint:** `GET /health` exposes server version, model name, and hot worker status for proxies and Docker healthchecks.

## 📦 Installation & Setup

### 1. Prerequisites (Debian/Ubuntu)
Install the following system dependencies first:
```bash
sudo apt update && sudo apt install -y espeak-ng curl file ffmpeg python3.12 python3.12-venv
```

> **Python version:** `setup.sh` requires **Python 3.12**. Python 3.13+ has no prebuilt wheels for `torch==2.9.0` or `torchcodec==0.8.1`. On systems where Python 3.12 is not the default (e.g. Ubuntu 24.10 with Python 3.14), the package above installs it alongside the system Python.

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
- **Elite/Custom Voices**: Reference voice files (.wav) for custom cloning are **not provided** due to copyright. Place your samples in `assets/voices/elite/` within the project directory.
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

## 📡 API Endpoints

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Server liveness, version, and hot worker status. |
| `GET` | `/v1/models` | OpenAI-compatible model list (`tts-1`, `tts-1-hd`). |
| `GET` | `/v1/voices` | List of available voice identifiers. |
| `POST` | `/v1/audio/speech` | Standard TTS synthesis (Hot or Cold Lane, cached). |
| `POST` | `/v1/audio/speech/stream` | Real-time streaming TTS (Hot Lane only, no cache). |

## 🔧 Troubleshooting

### Transformers Compatibility Error
The `isin_mps_friendly` compatibility fix is applied automatically as a Python monkey-patch in `main_tts.py` before any model import, and also by `setup.sh` as a fallback. No manual action is required.

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

| Variable | Default | Description |
| :--- | :--- | :--- |
| `TTS_MODEL` | `xtts_v2` | Model name to pre-load into the Hot Worker. |
| `DEFAULT_LANGUAGE` | `en` | Default language if not specified in the request. |
| `CACHE_TTL_MINUTES` | `10080` (7 days) | Cache file expiration. Set to `0` to disable. |
| `COLD_LANE_TIMEOUT_SECONDS` | `120` | Max time to wait for a Cold Lane subprocess before killing it and returning HTTP 500. |
| `DEBUG` | `false` | Set to `true` to enable worker routing traces. |
| `VENV_PYTHON` | *(auto-detected)* | Absolute path to the venv Python executable. |

*Note: All personality parameters listed in the section above can also be set via their respective `DEFAULT_*` environment variables.*

### 3. User Service (systemd --user)
1. Create directory if it doesn't exist: `mkdir -p ~/.config/systemd/user`
2. Create: `~/.config/systemd/user/coqui-tts.service`
3. Configuration (all environment variables are loaded from your `.env` file):

```ini
[Unit]
Description=Coqui TTS Local Server
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/coqui-tts-local-server
ExecStart=%h/coqui-tts-local-server/venv/bin/uvicorn main_tts:app --host 127.0.0.1 --port 5100
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

4. Enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable --now coqui-tts.service
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

## ☕ Support

If this project is useful to you, consider supporting its development:

- **Bitcoin (BTC):** `38jJyMomtUqhCjuNJ9VxKpgEyMyx37Zqix`
- **Monero (XMR):** `82bbUZdkMXUPAma4ioTuZNcJgTh8YTv4XNUwPy6T28kYJWCfeGgV79AZb7amCszFXeBaa5u595cQBVjFS4PkBGim56ap7Ej`
