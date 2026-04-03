# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.11] - 2026-04-03

### Fixed
- **`setup_assets.sh` voice download hangs on IPv6 tunnel systems:** Added `-4` flag to `curl` when downloading standard voices from `cdn.openai.com`. Azure CDN silently blocks TLS connections from Hurricane Electric tunnel broker ASNs (`2001:470::/32`), causing the download to hang indefinitely. IPv4 is unaffected.

## [1.4.10] - 2026-04-03

### Added
- **`GET /v1/models` endpoint:** OpenAI-compatible model listing returning `tts-1` and `tts-1-hd`. Required by clients (Open WebUI, SillyTavern, etc.) that query the model list before issuing TTS requests. The `model` field in synthesis requests continues to be accepted for spec compliance but is ignored internally.

### Changed
- **Version string moved to `SERVER_VERSION` constant:** `GET /health` now reads the version from this constant instead of a hardcoded string literal.

## [1.4.9] - 2026-04-02

### Fixed
- **Pinned dependencies to match production environment:** `torch==2.9.0`, `torchaudio==2.9.0`, `torchcodec==0.8.1`, `transformers>=4.35.2,<5.0.0`. Python 3.13+ has no prebuilt wheels for these packages; floating ranges (`>=2.1.0`) caused pip to resolve to newer versions incompatible with the installed CUDA NPP libraries.
- **`setup.sh` now selects python3.12:** Python 3.14 (system default on some Ubuntu 24.10 systems) has no wheels for torch 2.9.0 or torchcodec 0.8.1. `setup.sh` now checks for `python3.12` first and falls back to `python3` with a warning.

## [1.4.7] - 2026-04-03

### Fixed
- **Removed unnecessary `torchcodec` dependency:** `coqui-tts[codec]` changed to `coqui-tts` and `torchcodec` removed from `requirements.txt`. `torchcodec` is only used by the Bark model and audio dataset tooling — not by XTTS-v2. The dependency caused hot worker startup failure (`libnppicc.so.13: cannot open shared object file`) on systems where CUDA NPP libraries are not present.

## [1.4.8] - 2026-04-03

### Fixed
- **Reverted torchcodec stub monkey-patch:** The stub introduced in 1.4.7 was unnecessary on production systems where torchcodec installs correctly. Restored `torchcodec` as an explicit dependency in `requirements.txt`. Kept `transformers<5.0.0` pin.

## [1.4.7] - 2026-04-03

### Fixed
- **torchcodec / CUDA NPP startup crash:** `coqui-tts[codec]` is restored in `requirements.txt` (required for package metadata). `transformers` pins added (`<5.0.0` for GPT2PreTrainedModel compatibility with XTTS-v2). The torchcodec monkey-patch now catches `RuntimeError` in addition to `ImportError` and `OSError`, covering the case where the package is installed but `libnppicc.so.13` (CUDA NPP 13) is absent on CUDA 12.x systems. The stub is injected into `sys.modules` **before** any transformers import, ensuring `_torchcodec_available` is evaluated correctly. On systems where torchcodec cannot load its native library, the server starts in degraded mode (hot worker fails, cold lane still operational) rather than crashing.

## [1.4.6] - 2026-04-02

### Fixed
- **setup.sh hardcoded sentencepiece version:** Removed `pip install sentencepiece==0.2.0` from `setup.sh`. The package is already declared without a pin in `requirements.txt` and was being installed twice. The pinned version (`0.2.0`) had no prebuilt wheel for Python 3.14 and required a C/C++ compilation that could fail depending on the environment. pip now resolves the version from `requirements.txt` and picks a compatible prebuilt wheel.

## [1.4.5] - 2026-04-02

### Fixed
- **transformers monkey-patch:** The `isin_mps_friendly` compatibility fix (required by Coqui 0.27.5) is now applied as a Python monkey-patch in `main_tts.py` before the `TTS` import, instead of relying solely on `setup.sh` appending to the installed venv file. The new approach survives `pip install --upgrade transformers` without breaking. The `setup.sh` patch is retained as a redundant fallback with an explanatory comment.

## [1.4.4] - 2026-04-02

### Fixed
- **ffmpeg error information leak:** `subprocess.CalledProcessError` is now caught inside `convert_audio()` and re-raised as a generic `RuntimeError`. The client receives `"Audio conversion to <fmt> failed (ffmpeg exited <code>)"` instead of the full command string with internal temp file paths. Full error detail is still logged to stdout.

## [1.4.3] - 2026-04-02

### Fixed
- **Degraded mode visibility:** If the hot worker fails to load at startup, the error message is now stored in `hot_worker_error` (global) and exposed in `GET /health` as `"hot_worker_error": "<reason>"`. Previously the server started silently in degraded mode with no observable signal beyond a console print. Operators and proxies can now detect this state by polling `/health`.

## [1.4.2] - 2026-04-02

### Fixed
- **Cold Lane timeout:** `process.communicate()` now wrapped in `asyncio.wait_for()`. If the subprocess exceeds `COLD_LANE_TIMEOUT_SECONDS` (default: 120s, configurable via `.env`), the process is killed and the request fails with HTTP 500. Prevents hung subprocesses (OOM, driver crash) from blocking the server indefinitely.
- **Cache race condition:** Two concurrent requests with the same cache key no longer both synthesize the same audio. A per-key `asyncio.Lock` (stored in module-level `_cache_locks` dict) serializes access to the cache-check + synthesis + write block. The second request waits for the lock, then finds the file already written and returns it from cache.

## [1.4.1] - 2026-04-02

### Security
- **[CRITICAL] Cold Lane code injection fix:** The synthesis text passed to the Cold Lane subprocess was previously interpolated directly into a Python f-string (`text=\"\"\"{text}\"\"\"`). An input containing triple-quotes (`"""`) or escape sequences could break the string literal and inject arbitrary Python code executed by the subprocess. Text is now passed exclusively via the `TTS_INPUT_TEXT` environment variable and read inside the subprocess with `os.environ['TTS_INPUT_TEXT']`, completely isolating it from the generated code string.

## [1.4.0] - 2026-04-02

### Added
- **Streaming TTS Endpoint:** New `POST /v1/audio/speech/stream` for real-time audio delivery via chunked WAV transfer.
  - Uses XTTS-v2's `inference_stream()` on the Hot Lane only.
  - Returns HTTP 503 if the hot worker is not loaded or is busy.
  - A synchronous producer thread feeds PCM chunks into an `asyncio.Queue`, bridging the blocking model iterator with the async response generator without blocking the event loop.
  - Output: WAV (PCM 16-bit, mono, 24000 Hz) with standard streaming header (`data_size=0xFFFFFFFF`).
  - No caching — audio is generated and sent in real time.
  - Accepts the same JSON / form-data fields as `POST /v1/audio/speech`.

## [1.3.0] - 2026-04-02

### Added
- **Health Endpoint:** New `GET /health` endpoint returning server status, version, model name, and hot worker load state. Suitable for proxies, load balancers, and Docker healthchecks.
- **Cache TTL Expiration:** Cache files are now expired based on `CACHE_TTL_MINUTES` env var (default: 10080 = 7 days). Set to `0` to disable expiration. Added to `.env.example`.

## [1.2.0] - 2026-03-03

### Added
- **Personality Tuning:** Full support for `temperature`, `length_penalty`, `repetition_penalty`, `top_k`, and `top_p`.
- **Environment Configuration:** Personality defaults are now configurable via `.env` file (`DEFAULT_TEMPERATURE`, etc.).
- **Dynamic Language:** Added support for explicit `language` parameter in requests.
- **Improved Detection:** Smart `.env` and `venv` detection (searching in root and `bin/` subdirectories) for agnostic execution.
- **Documentation:** Added `.env.example` for easier deployment.

### Changed
- **API Parity:** Refactored Cold Lane (Child Lane) to use Python API instead of `tts` binary, ensuring identical behavior across all worker lanes.

## [1.1.4] - 2026-02-28

### Added
- **Stable Production Release:** Golden version for the Uttera.
- Performance verified on Sphinx and local nodes (3 concurrent streams in ~18s).
- Full architectural symmetry between production and repository branches.

### Changed
- Refined `main_tts.py` header with official Copyright and Architecture summary.

## [1.1.3] - 2026-02-28

### Fixed
- Corrected CLI flags in Child Lane (`--no-progress_bar` and `--use_cuda`) for compatibility with local `tts` binary, resolving "unrecognized arguments" errors.

## [1.1.2] - 2026-02-28

### Fixed
- Resolved function name mismatch in `create_speech` router (`run_tts_child_lane` vs `run_tts_child_lane_async`).

## [1.1.1] - 2026-02-28

### Added
- Restored `DEBUG` mode verbosity by disabling subprocess output capture and forcing `flush=True` on all prints.
- Detailed error reporting for FFmpeg and Subprocess failures.

## [1.1.0] - 2026-02-28

### Added
- Full architectural restoration from production `v123` reference (Sphinx node).
- Implementation of `asyncio.create_subprocess_exec` with pipe consumption to bypass GIL and prevent buffer deadlocks.
- Support for Stark Elite voice gallery (a character, a voice, a character, etc.) and Spanish by default.
- Modernized `requirements.txt` and `setup.sh` with hotfixes for Python 3.14 stability.

## [1.0.6] - 2026-02-28

### Added
- Consolidated architecture headers and GNU GPL v3 license from reference implementation.
- Detailed description of the hybrid concurrency model (Hot/Cold workers).

## [1.0.3] - 2026-02-28

### Added
- Complete No-Sudo installation workflow.
- Local directory structure within the project folder for `assets/` (models, voices, cache).
- Prerequisites section in README for `espeak-ng`, `curl`, and `file`.

## [1.0.0] - 2026-02-27

### Added
- Initial stable production release.
- End-to-end voice cloning pipeline documentation.
- Support for character voice engineering and specialized synthesis.
