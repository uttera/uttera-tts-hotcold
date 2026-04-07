# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased — experimental-py311]

### Changed
- **Python 3.11 as recommended runtime:** `setup.sh` (v1.1.4) now targets Python 3.11 instead of
  Python 3.12. Measured VRAM footprint with identical torch==2.9.0+cu128 + TTS 0.27.5 stack:
  **Python 3.11 = 4362 MiB vs Python 3.13 = 8132 MiB** (−3.77 GB per instance). This difference
  is structural (not runtime accumulation) — confirmed by clean restarts with empty cache at both
  versions. Python 3.11.15 confirmed compatible with the full dependency tree.
  Install: `sudo apt install python3.11 python3.11-venv python3.11-dev`

### Validated
- 40-clip Spanish stress test (same test vectors as v1.5.7 validation) against Python 3.11 server
  (venv311, clean cache): **40/40 OK, 0 errores**. Latency avg=22.88s, min=3.16s, max=51.74s.
  Audio quality identical. Cold EMA calibrated at 22.76s. VRAM grew only 0.36 GB over the full
  run (10.25 → 9.89 GB free). Functionally equivalent to Python 3.13 results (avg 23.35s).

---

## [1.5.7] - 2026-04-07

### Added
- **Cold lane WAV-missing diagnostic:** When the cold subprocess exits with code 0 but produces no output WAV (empty text, silent crash, driver issue), full `stdout` and `stderr` are now logged and a descriptive `RuntimeError("Cold Lane produced no output (exit 0, WAV missing)")` is raised instead of the opaque downstream error at `convert_audio`. Mirrors the JSON-missing diagnostic introduced in whisper-stt-local-server v1.4.7.
- **`cold_workers_in_flight` added to `GET /health`:** The count of currently active cold lane subprocesses is now exposed under `smart_routing` alongside `vram_free_gb` and `vram_sufficient_for_cold`, consistent with whisper-stt-local-server v1.4.7.

### Validated
- 40-clip Spanish stress test comparing v1.5.7 (local, 16.99 GB VRAM free) vs v1.4.10 (sphinx, production, caché limpia). Four waves: 10 concurrent, 10 staggered @0.2s, 10 concurrent, 10 staggered @0.1s.
  - **v1.5.7: 40/40 OK, 0 errores.** VRAM pre-check + cold→hot fallback absorben toda la carga: hot lane avg 4-9s, cold lane avg 30-49s, cold EMA calibrado en ~30s, máx 3 workers concurrentes con `MIN_COLD_VRAM_GB=5.0`.
  - **v1.4.10: 13/40 OK, 27/40 ERR HTTP 500.** Sin VRAM pre-check ni fallback, los cold workers hacen OOM al cargar XTTS-v2 simultáneamente y el error llega directamente al cliente. W3 (10 concurrent con hot ocupado) produjo 9/10 errores. Los 13 OK corresponden exactamente a las requests que pillaron el hot lane libre.
  - El test cuantifica el impacto real de v1.5.0–v1.5.6: **tasa de error 67.5% → 0%** bajo carga concurrente.

## [1.5.6] - 2026-04-06

### Added
- **VRAM pre-check before cold lane dispatch:** Branch C now calls `torch.cuda.mem_get_info()` before spawning a cold subprocess. If effective free VRAM (raw free minus `in_flight × MIN_COLD_VRAM_GB`) is below `MIN_COLD_VRAM_GB` (default `5.0` GB for XTTS-v2, configurable via `.env`), the request is rerouted to the hot lane queue immediately — avoiding the ~10s wasted loading the model before OOM. The in-flight reservation prevents burst routing from over-committing VRAM before any subprocess has allocated. `vram_free_gb`, `min_cold_vram_gb`, `cold_workers_in_flight`, and `vram_sufficient_for_cold` added to `GET /health` under `smart_routing`. Set `MIN_COLD_VRAM_GB=0` to disable. Same feature applied to whisper-stt-local-server v1.4.7 (default `4.0` GB).

## [1.5.5] - 2026-04-06

### Fixed
- **`model_lock` deadlock under client timeout:** Branch B and the Branch C fallback previously used two separate `asyncio.to_thread` calls — one to acquire `model_lock` and one to run synthesis. If asyncio cancelled the coroutine (e.g. client timeout during burst load) between the two awaits, `model_lock` was left permanently acquired with no one to release it, deadlocking the server for all subsequent requests. Fixed by introducing `_run_tts_hot_locked()`, which performs acquire + synthesize + release inside a single `asyncio.to_thread` call. Same fix applied to whisper-stt-local-server v1.4.5.

## [1.5.4] - 2026-04-06

### Added
- **Auto-Calibration of `COLD_START_TIME_SECONDS`:** The router now measures each successful cold lane completion and maintains an EMA (α = 0.2) of cold lane times in `_cold_ema_start`. Once seeded, `_get_cold_start_time()` returns the live EMA instead of the static `COLD_START_TIME_SECONDS`, so the routing threshold self-adjusts to actual hardware performance without manual tuning. `COLD_START_TIME_SECONDS` in `.env` becomes an initial hint / fallback used only before the first successful cold lane completes. `cold_start_calibrated`, `cold_ema_start_seconds`, and `cold_start_configured_seconds` added to `GET /health` under `smart_routing`.

## [1.5.3] - 2026-04-06

### Fixed
- **EMA not updated from fallback path:** The cold-lane fallback was calling `_update_hot_ema` with an elapsed time that included the cold-lane failure duration (~`COLD_START_TIME_SECONDS`). This inflated `ema_spw` after each fallback, causing the router to dispatch cold lanes more aggressively on subsequent bursts — a positive feedback loop (more OOMs → more fallbacks → higher EMA → more cold dispatches → more OOMs). The EMA is now updated only from clean Branch A and Branch B completions. The same fix was applied to both fallback paths in whisper-stt-local-server.

## [1.5.2] - 2026-04-06

### Added
- **Cold-Lane Fallback to Hot Lane:** When a cold lane subprocess exits with a non-zero code (CUDA OOM under burst load), the request is transparently retried on the hot lane queue instead of returning HTTP 500. Uses the same Branch-B queuing mechanism — `word_count` is added to `_hot_queue_words` before waiting so late-arriving requests see the correct queue depth. Mirrors the behaviour introduced in whisper-stt-local-server v1.4.1.

### Changed
- **Warmup text extended to 8 words** (`"All systems nominal. Standing by for further orders."`). The previous 2-word text (`"System online."`) produced an initial `ema_spw` ~2× higher than the real-workload average, causing the router to dispatch cold lanes too aggressively on the first burst after startup.

## [1.5.1] - 2026-04-06

### Added
- **Startup EMA Warmup:** After the hot worker loads, a short synthesis (`"System online."`) is run through the hot lane via the FastAPI lifespan event to seed `_hot_ema_spw` before the first real request arrives. Without this, `EMA=None` at startup caused every concurrent request to go to cold lane (Branch C), triggering CUDA OOM when multiple workers tried to load the model simultaneously. The warmup runs before `Application startup complete` (blocking the event loop intentionally, since no requests can arrive yet), and prints the measured `spw` on the console so the operator can verify hardware throughput at startup. Failure is logged but non-fatal: the server starts in uncalibrated mode rather than refusing to start.

## [1.5.0] - 2026-04-06

### Added
- **Smart Hot-Lane Routing:** The router now uses a three-branch decision instead of the previous binary hot/cold split.
  - **Branch A** (hot lane free): use it immediately — unchanged from prior behaviour.
  - **Branch B** (hot lane busy, worth waiting): if the estimated queue drain time is below `COLD_START_TIME_SECONDS × HOT_QUEUE_SAFETY_FACTOR`, the request waits for the hot lane via a non-blocking `asyncio.to_thread(model_lock.acquire)` instead of spawning a cold subprocess. This eliminates unnecessary cold-lane spawns for short and medium requests when the hot lane is lightly backlogged.
  - **Branch C** (hot lane busy, cold is faster): drain estimate exceeds threshold → spawn cold lane as before.
  - The drain estimate is computed from `_hot_queue_words × ema_spw`, where `_hot_queue_words` counts all words currently in the hot pipeline (being synthesised + queued waiting), ensuring late-arriving requests always see the full accumulated depth.
  - The EMA (α = 0.2) is updated after each successful hot-lane synthesis and self-calibrates to the actual hardware throughput. Falls back to Branch C (cold lane) when not yet calibrated.
  - New env vars: `COLD_START_TIME_SECONDS` (default `10.0` s — measure once on your hardware), `HOT_QUEUE_SAFETY_FACTOR` (default `0.8`).
  - Routing decision and live telemetry (`ema_spw`, `hot_queue_words`, `hot_queue_drain_estimate_seconds`, `threshold_seconds`) exposed in `GET /health` under `smart_routing`.

### Performance (verified on RTX 50-series, XTTS-v2, cold start ≈ 10 s)
- **3 concurrent requests** (6–12 words each): all routed to hot lane queue. Total wall time **4.4 s**. Without smart routing, req2 and req3 would have each waited ~10 s for a cold lane to load.
- **6 concurrent requests** (6–25 words): first 3 hot-queued (drain estimates 2.4 s, 6.1 s — below 8 s threshold). Last 3 dispatched to cold lanes when accumulated drain reached **10.5 s > 8.0 s** threshold. Cold workers ran in parallel; req4–6 resolved in ~22 s. Router correctly identified the crossover point.

## [1.4.12] - 2026-04-04

### Added
- **Official Docker Support:** Fully containerized deployment using NVIDIA CUDA 12.6 on Ubuntu 24.04 base.
- **Auto-Provisioning Entrypoint:** Automated model download (XTTSv2) and voice gallery setup on first run.
- **GPU Acceleration:** Robust GPU passthrough configuration for NVIDIA RTX 50-series hardware.
- **Documentation:** Comprehensive Docker installation and execution guides added to README.md.

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
