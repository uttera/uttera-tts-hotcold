# TTS Backend Plugin Architecture

uttera-tts-hotcold supports **multiple TTS engines** through a plugin
system. Each engine is a Python module under `backends/` that implements
the `TTSBackend` abstract interface. The server code (`main_tts.py`,
`cold_worker_tts.py`) is backend-agnostic — it interacts only with the
`TTSBackend` methods.

## Available backends

| Backend | Module | Model | License | Output | Languages | Streaming |
|---|---|---|---|---|---|---|
| **coqui** (default) | `backends/coqui_backend.py` | XTTS-v2 | CPML (non-commercial) | 24 kHz | 16 | Yes |
| **voxcpm** | `backends/voxcpm_backend.py` | VoxCPM2 | Apache-2.0 | 48 kHz | 30 | Yes |

## Selecting a backend

Set the `TTS_BACKEND` environment variable before starting the server:

```bash
# Coqui (default if TTS_BACKEND is unset)
TTS_BACKEND=coqui uvicorn main_tts:app --port 9004

# VoxCPM2
TTS_BACKEND=voxcpm uvicorn main_tts:app --port 9004
```

The same variable is forwarded to cold worker subprocesses automatically.

## Installing backend dependencies

Each backend has its own requirements file. Install **one** of:

```bash
pip install -r requirements-coqui.txt    # Coqui XTTS-v2
pip install -r requirements-voxcpm.txt   # VoxCPM2
```

Both include the base `requirements.txt` automatically.

**Do not install both in the same venv** unless you are certain the torch
versions are compatible. Coqui pins `torch<2.10`; VoxCPM needs `torch>=2.6`.

## Personality parameters

The API accepts parameters from all backends in the same request body.
Each backend uses the ones it understands and ignores the rest.

### Coqui parameters (autoregressive token sampling)

| Parameter | Default | Effect |
|---|---|---|
| `temperature` | 0.75 | Randomness in GPT-2 token sampling. Higher = more expressive |
| `length_penalty` | 1.0 | Penalizes long sequences. >1 = shorter output |
| `repetition_penalty` | 5.0 | Penalizes repeated tokens. Prevents loops |
| `top_k` | 50 | Limits sampling to top K tokens |
| `top_p` | 0.85 | Nucleus sampling threshold |

### VoxCPM parameters (diffusion)

| Parameter | Default | Effect |
|---|---|---|
| `cfg_value` | 2.0 | Classifier-free guidance. Higher = closer to reference voice |
| `inference_timesteps` | 10 | Diffusion steps. More = better quality, slower |

### Cross-backend mapping

When a client sends `temperature` to VoxCPM (which has no token sampling),
the backend maps it to `cfg_value` automatically:

```
cfg_value = 3.5 - temperature × 2.0
```

If both `temperature` and `cfg_value` are present, `cfg_value` takes
priority in the VoxCPM backend.

## Voice selection

Both backends use the same voice resolution system:

1. `voices.json` maps voice names to WAV file paths
2. The server resolves the path and passes it to `backend.infer(voice_wav_path=...)`
3. Coqui uses it as `speaker_wav` for conditioning
4. VoxCPM uses it as `prompt_wav_path` for voice cloning

The same `voices.json` and voice files work with both backends.

## Adding a new backend

1. Create `backends/<name>_backend.py` with a `Backend` class inheriting
   from `TTSBackend`.

2. Implement all abstract methods: `load()`, `infer()`, `unload()`,
   `supported_languages()`. Optionally override `infer_stream()`.

3. Set `name` and `supports_streaming` class attributes.

4. Create `requirements-<name>.txt` with `-r requirements.txt` plus the
   backend-specific dependencies.

5. The factory (`backends/__init__.py`) will find your module automatically
   when `TTS_BACKEND=<name>` is set.

### Backend contract summary

```python
class Backend(TTSBackend):
    name = "myengine"
    supports_streaming = False  # or True

    def load(self, device="cuda", precision="fp32"):
        """Load model. Called once per process."""

    def infer(self, text, voice_wav_path, language, speed=1.0, params=None) -> bytes:
        """Return complete WAV bytes."""

    def infer_stream(self, text, voice_wav_path, language, speed=1.0, params=None):
        """Yield WAV header + PCM chunks. Only if supports_streaming=True."""

    def unload(self):
        """Free resources. Must be idempotent."""

    def supported_languages(self) -> list[str]:
        """Return ISO language codes. Callable before load()."""
```

### Rules for backend authors

- **stdout is reserved** for the cold worker JSON protocol. All diagnostic
  logging MUST go to `sys.stderr`.
- `infer()` returns **complete WAV bytes** (RIFF header + PCM data).
- `params` dict may contain keys from ANY backend. Ignore unknown keys.
- `load()` failure = raise exception. The server treats it as fatal for
  that worker.
- `unload()` must be idempotent — calling twice is a no-op.

## Docker

Build for a specific backend:

```bash
docker build --build-arg TTS_BACKEND=coqui -t uttera-tts-hotcold:coqui .
docker build --build-arg TTS_BACKEND=voxcpm -t uttera-tts-hotcold:voxcpm .
```

Or with docker compose:

```bash
TTS_BACKEND=voxcpm docker compose up -d
```

## Architecture diagram

```
Client
  │
  ▼
main_tts.py (FastAPI)
  │ TTS_BACKEND env var
  ▼
backends/__init__.py → load_backend()
  │
  ├─ TTS_BACKEND=coqui  → backends/coqui_backend.py  → Coqui TTS library
  ├─ TTS_BACKEND=voxcpm  → backends/voxcpm_backend.py → voxcpm library
  └─ TTS_BACKEND=<new>   → backends/<new>_backend.py  → your engine
  │
  ▼
Hot Worker (model resident in VRAM)
  + Cold Pool (subprocesses, same backend via cold_worker_tts.py)
```
