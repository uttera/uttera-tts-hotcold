# uttera-tts-hotcold

<p align="center">
  <a href="https://uttera.ai">
    <img src="docs/img/banner.png" alt="uttera.ai — The voice layer for your AI" width="800">
  </a>
</p>

High-performance TTS API server with a hybrid "Hot/Cold" worker architecture and **pluggable backends** (Coqui XTTS-v2, VoxCPM2, and more).

**Ideal for locally running installations of agents like OpenClaw or Open-WebUI, where the media should not leave the private local domain.**

**Backends:** switch TTS engine with a single env var — `TTS_BACKEND=coqui` or `TTS_BACKEND=voxcpm`. See [docs/backends.md](docs/backends.md) for the full plugin architecture documentation.

> ⚠️ **VoxCPM2 backend — not recommended for production.** VoxCPM2's `torch.compile` / CUDA Graph path is incompatible with hot/cold's multi-process subprocess pool and triggers a CUDA allocator race under concurrent load. Confirmed upstream by the VoxCPM maintainers in [OpenBMB/VoxCPM#269](https://github.com/OpenBMB/VoxCPM/issues/269), who explicitly recommend a single-process runtime (`nano-vllm-voxcpm` / `vllm-omni`) for concurrent serving. For VoxCPM2 in production use [`uttera-tts-vllm`](https://github.com/uttera/uttera-tts-vllm) (the nano-vllm-voxcpm wrapper) — it delivers 1024/1024 OK at burst@1024 on the same GPU. The voxcpm backend in this repo remains available for dev / single-request / bench purposes and ships a runtime warning at load time.

> **Created and maintained by [Hugo L. Espuny](https://github.com/fakehec).**
> Part of the [Uttera](https://uttera.ai) voice stack.
> Source code licensed under the [Apache License 2.0](LICENSE).
> See [NOTICE](NOTICE) for third-party attributions.

## 📢 Project history: renamed and transferred

This repository has been **renamed** from `coqui-tts-local-server` to
**`uttera-tts-hotcold`** and **transferred** from its original creator's
personal page ([@fakehec](https://github.com/fakehec)) to the
[Uttera GitHub organization](https://github.com/uttera).

GitHub redirects old URLs automatically, so any existing clones, forks,
bookmarks, and links keep working. If you still have
`fakehec/coqui-tts-local-server` as your `origin`, consider updating:

```bash
git remote set-url origin https://github.com/uttera/uttera-tts-hotcold.git
```

The v2.0.0 release (April 2026) introduced the plugin backend
architecture — Coqui XTTS-v2 and VoxCPM2 both live behind the
`TTS_BACKEND` env var, selectable per deployment. The codebase is
[Apache-2.0](LICENSE) since v2.0.0; see [HISTORY.md](HISTORY.md) and
[NOTICE](NOTICE) for the full transition context.

## ⚖️ License & model licensing (IMPORTANT)

**Server source code** (this repository): Apache License 2.0. See
[LICENSE](LICENSE). Commercial use permitted.

**Default TTS model (XTTS-v2)**: released by Coqui under the Coqui Public
Model License (CPML).
- **NON-COMMERCIAL USE ONLY**: the XTTS-v2 weights are free for personal
  and non-commercial projects.
- **COMMERCIAL USE**: If you intend to use this for commercial purposes, you **must** purchase a commercial license from Coqui (licensing@coqui.ai).
- By running the installation scripts, you acknowledge and agree to these terms.

## 🚀 Key Features

*Concurrency and engines*
- **Hybrid hot/cold pool:**
  - **Hot worker:** primary model resident in VRAM for sub-second
    (XTTSv2 ~1.0 s) inference.
  - **Cold workers:** on-demand subprocesses spawned on GPU when the
    main lane is busy. Drains idle after `COLD_WORKER_IDLE_TIMEOUT`.
- **Pluggable backends** (`TTS_BACKEND=coqui|voxcpm`) — switch engine
  with one env var. See [docs/backends.md](docs/backends.md).
- **GPU accelerated** via `torch` + CUDA (NVIDIA).

*OpenAI-compatible API*
- Standard params: `model`, `voice`, `speed`, `response_format`.
- `GET /v1/models` for client autodiscovery (reports `tts-1` and
  `tts-1-hd`, `owned_by: uttera`).
- **Streaming** via `POST /v1/audio/speech/stream` (chunked WAV,
  XTTS-v2 `inference_stream()`, Hot Lane only, no cache).
- **Adhoc voice cloning** via `custom_voice_file` multipart upload on
  `/v1/audio/speech` (legacy alias `speaker_wav` also accepted).
  Upload lives one request, no state persisted.
- 5 response formats: MP3, WAV, PCM, Opus, FLAC.

*Validation and observability*
- Strict validation on every knob — out-of-range returns HTTP 422
  with a useful detail body:
  - `speed` ∈ `[0.25, 4.0]` (OpenAI spec)
  - `temperature` ∈ `[0.0, 2.0]` (Coqui safe range)
  - `cfg_value` ∈ `[0.5, 5.0]` (VoxCPM safe range)
  - `response_format` must be one of `mp3|wav|pcm|opus|flac`
  - Unknown `voice` → HTTP 400 with the list of available voices
    (v2.2.0 closed the silent-fallback regression)
- `X-Route` response header — `HOT` / `COLD-POOL` / `COLD-POOL>HOT` /
  `ADHOC` — tells the client which lane handled the request.
- `X-Cache` response header — `HIT` / `MISS` / `BYPASS` / `ADHOC` /
  `DISABLED` — verifies the cache decision without timing heuristics.

*Personality*
- `temperature`, `top_k`, `top_p`, `length_penalty`, `repetition_penalty`
  exposed as request fields and env defaults.
- 16-language XTTS-v2 coverage: `en, es, fr, de, it, pt, pl, tr, ru, nl,
  cs, ar, zh-cn, hu, ko, ja` (English default).

*Caching and privacy*
- MD5-based audio cache keyed by `(model, voice, speed, format, params,
  text)`. TTL via `CACHE_TTL_MINUTES`.
- **Per-request cache opt-out** — three equivalent mechanisms:
  JSON body `{"cache": false}`, multipart form `cache=false|0|no|off`,
  or the standard HTTP header `Cache-Control: no-cache`. See
  [API.md §3](API.md#cache-opt-out--per-request-privacy-control).
- Adhoc voice-cloning requests always bypass the cache (`X-Cache: ADHOC`).

*Operations*
- `GET /health` **and `HEAD /health`** expose version, backend, model,
  worker status, queue depth, VRAM — one struct for both proxies and
  Docker healthchecks.
- Opt-in `CORSMiddleware` via `CORS_ALLOW_ORIGINS` env var (disabled
  by default — API-first deployments don't need it).
- Canonical Uttera-stack port **`9004`** (TTS family). STT family
  uses `9005`. Swapping `hotcold ↔ vllm` is a backend change, not a
  port change.
- Optional Redis self-registration for upstream router discovery —
  same protocol as the sibling `uttera-tts-vllm` and STT servers.

## 📦 Installation & Setup

### 1. Prerequisites (Debian/Ubuntu)
Install the following system dependencies first:
```bash
sudo apt update && sudo apt install -y espeak-ng curl file ffmpeg python3 python3-venv
```

> **Python version:** `setup.sh` uses the system default `python3` (3.12+ recommended). torch is pinned to `>=2.9.0,<2.10.0` to avoid CUDA 13 NPP dependency issues with newer versions.

### 2. Unified Installation
```bash
git clone https://github.com/uttera/uttera-tts-hotcold.git
cd uttera-tts-hotcold
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
The server listens on port `9004` by default. Ensure the user has permissions to open sockets on this port (standard for ports >1024).

### 4. Vocal Provisioning
- **Standard Voices**: `setup_assets.sh` provisions the 6 standard OpenAI identities (Alloy, Echo, Fable, Onyx, Nova, Shimmer) into `assets/voices/standard/`.
- **Elite/Custom Voices**: Reference voice files (.wav) for custom cloning are **not provided** due to copyright. Place your samples in `assets/voices/elite/` and register them in `voices.json` (e.g. `"narrator": "elite/narrator.wav"`). No code changes required.
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
| `GET` / `HEAD` | `/health` | Server liveness, version, backend, model, worker status, queue, VRAM. |
| `GET` | `/v1/models` | OpenAI-compatible model list (`tts-1`, `tts-1-hd`; `owned_by: uttera`). |
| `GET` | `/v1/voices` | List of available voice identifiers. |
| `POST` | `/v1/audio/speech` | Standard TTS synthesis (Hot or Cold Lane, cached; multipart supports adhoc voice cloning via `custom_voice_file`). |
| `POST` | `/v1/audio/speech/stream` | Real-time streaming TTS (Hot Lane only, no cache, registered voices only). |

See [API.md](API.md) for full request/response schemas, validation
ranges, `X-Cache`/`X-Route` semantics, and the cache opt-out contract.

## 🔧 Troubleshooting

### Transformers Compatibility Error
The `isin_mps_friendly` compatibility fix is applied automatically as a Python monkey-patch in `main_tts.py` before any model import, and also by `setup.sh` as a fallback. No manual action is required.

## 🛠 Execution

The server uses direct **Uvicorn** execution for maximum ASGI performance.

### Manual Execution (Console)
```bash
source venv/bin/activate

# Localhost only (Default: 127.0.0.1:9004)
uvicorn main_tts:app --host 127.0.0.1 --port 9004

# Expose to Local Network (0.0.0.0)
uvicorn main_tts:app --host 0.0.0.0 --port 9004
```

### ⚙️ Environment Variables & .env

The server includes a `.env.example` file. You can create a **`.env`** file in the root directory to override default behaviors without changing the code.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `TTS_MODEL` | `xtts_v2` | Model name to pre-load into the Hot Worker. |
| `COQUI_PRECISION` | `fp32` | Model precision: `fp32`, `fp16`, or `bf16`. |
| `DEFAULT_LANGUAGE` | `en` | Default language if not specified in the request. |
| `CACHE_TTL_MINUTES` | `10080` (7 days) | Cache file expiration. Set to `0` to disable. |
| `COLD_POOL_SIZE` | `6` | Max concurrent cold workers (safety cap). |
| `COLD_WORKER_IDLE_TIMEOUT` | `60` | Seconds before idle cold worker exits. |
| `COLD_WORKER_IDLE_STAGGER` | `10` | Stagger per worker slot to avoid mass die-off. |
| `MIN_COLD_VRAM_GB` | `2.5` | Min free VRAM to spawn a cold worker (0=disable). |
| `ROUTING_DRAIN_CAP_SECONDS` | `120` | Queue drain time considered 100% load. |
| `REDIS_URL` | *(empty)* | Redis URL for node self-registration (opt-in). |
| `NODE_HOST` | `localhost` | Host advertised to Redis for Gatekeeper routing. |
| `NODE_PORT` | `9004` | Port advertised to Redis for Gatekeeper routing. |
| `DEBUG` | `false` | Set to `true` to enable worker routing traces. |
| `VENV_PYTHON` | *(auto-detected)* | Absolute path to the venv Python executable. |

*See `.env.example` for the full list including personality defaults (`DEFAULT_TEMPERATURE`, etc.).*

### 3. User Service (systemd --user)
1. Create directory if it doesn't exist: `mkdir -p ~/.config/systemd/user`
2. Create: `~/.config/systemd/user/uttera-tts.service`
3. Configuration (all environment variables are loaded from your `.env` file):

```ini
[Unit]
Description=Uttera TTS Hot/Cold Server
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/uttera-tts-hotcold
ExecStart=%h/uttera-tts-hotcold/venv/bin/uvicorn main_tts:app --host 127.0.0.1 --port 9004
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

4. Enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable --now uttera-tts.service
```

## 🐳 Docker

### Host Prerequisites (one-time setup)

Before running `docker compose up` for the first time, the host machine requires two one-time configuration steps to enable GPU passthrough via the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) CDI mode.

> These steps are required because Docker's default legacy GPU mode relies on BPF cgroup device filters, which are not available in cgroup v2 environments (Ubuntu 22.04+). CDI solves this cleanly.

**1. Add the NVIDIA package repository:**
```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

**2. Install the toolkit:**
```bash
sudo apt update && sudo apt install -y nvidia-container-toolkit
```

**3. Generate the CDI spec** (exposes the GPU to containers via a stable device descriptor):
```bash
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
```

**4. Enable CDI in the Docker daemon:**
```bash
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "features": {
    "cdi": true
  }
}
EOF
sudo systemctl restart docker
```

**5. Verify it works:**
```bash
docker run --rm --device nvidia.com/gpu=all nvidia/cuda:12.6.3-runtime-ubuntu24.04 nvidia-smi
```

> **Note:** Step 3 must be re-run if the NVIDIA driver is updated (`sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`).

### Running with Docker Compose

```bash
# Build and start (downloads model and standard voices on first run)
docker compose up -d

# Check server is ready
curl http://localhost:9004/health

# View logs (including first-run provisioning progress)
docker compose logs -f

# Stop
docker compose down
```

On first run, `entrypoint.sh` automatically:
- Downloads the `xtts_v2` model (~1.7GB) into `assets/models/`
- Downloads the 6 standard voices (alloy, echo, fable, onyx, nova, shimmer) into `assets/voices/standard/`

Both are persisted in host volumes and skipped on subsequent starts.

### Elite Voices in Docker

Elite/custom voices are not provisioned automatically. Mount them into the container by placing your `.wav` files in `assets/voices/elite/` on the host — the volume mapping `./assets/voices:/app/assets/voices` picks them up automatically without rebuilding the image.

## 📊 Observability (`/metrics`)

`GET /metrics` returns Prometheus-format metrics for direct scraping
by Prometheus, Telegraf's `inputs.prometheus` plugin, or any other
OpenMetrics-compatible consumer. Metrics share the `uttera_tts_*`
namespace with the sibling `uttera-tts-vllm` backend (same names
and label shapes for the common series — the `engine` label in
`uttera_tts_build_info` differentiates the variant, carrying the
active `TTS_BACKEND` for this hotcold backend), plus this server's
additional hot/cold pool telemetry.

```toml
[[inputs.prometheus]]
  urls = ["http://tts-host:9004/metrics"]
  interval = "15s"
```

Key series:

| Metric | Type | Use |
|---|---|---|
| `uttera_tts_requests_total{endpoint,method,status}` | Counter | Per-endpoint request rate + status mix |
| `uttera_tts_request_duration_seconds{endpoint,method}` | Histogram | HTTP p50/p95/p99 (total RTT) |
| `uttera_tts_inflight_requests` | Gauge | Live load (hot + cold combined) |
| `uttera_tts_requests_by_route_total{route}` | Counter | Lane split — `HOT` / `COLD-POOL` / `COLD-POOL>HOT` / `CACHE` / `ADHOC` |
| `uttera_tts_synthesis_total{response_format,route,cache}` | Counter | Traffic mix across format × lane × cache decision (same semantics as `X-Route`/`X-Cache` headers) |
| `uttera_tts_characters_synthesised_total{response_format}` | Counter | Input chars synthesised — billing / throughput proxy. Cache hits don't re-bill |
| `uttera_tts_inference_duration_seconds{op}` | Histogram | Lane-tagged: `synthesis_hot` / `synthesis_cold` / `ffmpeg_encode` |
| `uttera_tts_voices_loaded` | Gauge | Count of voices in `voices.json` |
| `uttera_tts_cold_workers_active` | Gauge | Live cold subprocesses |
| `uttera_tts_cold_workers_loading` | Gauge | Cold subprocesses booting |
| `uttera_tts_cold_worker_pool_size_cap` | Gauge | `COLD_POOL_SIZE` |
| `uttera_tts_cold_workers_spawned_total` | Counter | Monotonic spawn count (for churn dashboards) |
| `uttera_tts_cold_worker_ema_start_seconds` | Gauge | Rolling EMA of cold-worker boot time |
| `uttera_tts_work_queue_depth` | Gauge | Items queued |
| `uttera_tts_work_queue_words` | Gauge | Words queued (for drain-time estimate) |
| `uttera_tts_load_score` | Gauge | Saturation signal `[0.0, 1.0]` |
| `uttera_tts_hot_ema_spw` | Gauge | Hot-lane seconds-per-word EMA |
| `uttera_tts_vram_free_gb` | Gauge | GPU memory headroom |
| `uttera_tts_vram_per_cold_worker_gb` | Gauge | Rolling EMA of VRAM per cold subprocess |
| `uttera_tts_engine_ready` | Gauge | 1 if hot worker backend loaded |
| `uttera_tts_errors_total{type}` | Counter | Typed errors (`decode` / `validation` / `model` / `encoding`) |
| `uttera_tts_build_info{version,engine,model}` | Gauge | Version + engine (`coqui` / `voxcpm`) + model in the field (value always `1`) |

## 🔒 Security & Network Note
By default, the server binds to **`127.0.0.1`** on port **`9004`**. 
- To allow external network access, modify the `--host` parameter to `0.0.0.0` in the execution command or systemd unit.
- **WARNING**: This API **does not have authentication**. Exposing it to the network via `0.0.0.0` represents a security risk. Ensure the server is protected by a firewall or operating within a secure VPN/Local Network.

## 📊 Performance (NVIDIA RTX 5090, fp32)
| Task | Latency |
| :--- | :--- |
| Single request (Hot Lane) | **~1.0s** |
| Cached response | **<0.02s** |
| 160 concurrent requests | 99.3s total, 1.61 req/s, **0 failures** |

## 🛡 License

**Server source code**: [Apache License 2.0](LICENSE). Commercial use permitted.

**Default TTS model (XTTS-v2)**: released by Coqui under the Coqui Public
Model License (CPML) — **non-commercial only**. See [NOTICE](NOTICE) and the
license section at the top of this README for details and commercial
alternatives.

Created and maintained by [Hugo L. Espuny](https://github.com/fakehec),
with contributions acknowledged in [AUTHORS.md](AUTHORS.md).

## ☕ Community

If you want to follow the project or get involved:

- ⭐ Star this repo to help discoverability.
- 🐛 Report issues via the [issue tracker](../../issues).
- 💬 Join the conversation in [Discussions](../../discussions).
- 📰 Technical posts at [blog.uttera.ai](https://blog.uttera.ai).
- 🌐 Uttera Cloud: [https://uttera.ai](https://uttera.ai) (EU-hosted,
  solar-powered, subscription flat-rate).

---

*Uttera /ˈʌt.ər.ə/ — from the English verb "to utter" (to speak aloud, to
pronounce, to give audible expression to). Formally, the name is a backronym
of **U**niversal **T**ext **T**ransformer **E**ngine for **R**ealtime **A**udio
— reflecting the project's origin as a STT/TTS server and its underlying
Transformer architecture.*
