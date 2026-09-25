#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Uttera TTS Server (Multi-Backend Hybrid)
#
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Hugo L. Espuny
# Original work created with assistance from Google Gemini and Anthropic Claude
#
# Part of the Uttera voice stack (https://uttera.ai).
# See LICENSE and NOTICE for full terms and attributions.
#
# main_tts.py - Uttera TTS Hybrid-Worker Server (plugin-based backends)
#
# Package: uttera-tts-hotcold
# Version: 2.4.2
# Maintainer: Uttera, Hugo L. Espuny
# Description: High-performance TTS server with pluggable engines (Coqui,
#              VoxCPM2, …), personality tuning, and GIL-bypass concurrency.
#
# CHANGELOG:
# - 2.4.2 (2026-04-21): setup.sh was tracked with mode 100644 (no exec
#   bit), so `./setup.sh` after a fresh `git clone` failed with
#   "Permission denied". Marked executable in the index (100755); no
#   runtime code change.
# - 2.4.1 (2026-04-21): Fix NameError in the 2.4.0 /metrics handler:
#   `_refresh_gauges_from_state()` referenced an undefined `voices`
#   when setting `_VOICES_LOADED_GAUGE`. Corrected to `VOICE_MAP`.
#   2.4.0 booted fine but the first scrape of /metrics would raise.
# - 2.4.0 (2026-04-21): Prometheus /metrics endpoint. Exposes the
#   shared uttera_tts_* HTTP + synthesis metrics (matching
#   uttera-tts-vllm v1.4.0 label shapes), plus hot/cold-specific
#   pool telemetry: requests_by_route_total{route}, cold_workers_active,
#   cold_workers_loading, cold_workers_spawned_total,
#   cold_worker_ema_start_seconds, work_queue_depth,
#   work_queue_words, load_score, hot_ema_spw, vram_free_gb,
#   vram_per_cold_worker_gb. Inference duration histogram ops are
#   lane-tagged: synthesis_hot / synthesis_cold / ffmpeg_encode.
#   build_info's `engine` label carries TTS_BACKEND so dashboards
#   can slice by coqui vs voxcpm. Additive — all existing endpoints
#   unchanged. Scrape with Telegraf's inputs.prometheus or any
#   OpenMetrics consumer.
# - 2.3.0 (2026-04-18): Default port migrated from 5100 → 9004.
#   Formalising the canonical Uttera-stack port scheme: all
#   Text-to-Speech backends (hotcold + vllm) default to port 9004,
#   all Speech-to-Text backends default to 9005. The Gatekeeper and
#   clients route by service family (TTS/STT) — swapping hotcold ↔
#   vllm is a backend change, not a port change. Rationale for
#   leaving 5100: while 5100 itself had no mainstream collisions,
#   pairing TTS on 5100 with STT on 9005 was asymmetric. The
#   9000-9099 range is IANA "User Ports" without canonical
#   assignment. Updated artefacts: `main_tts.py` runtime default,
#   `cold_worker_tts.py` (if port-aware), README + API.md URLs,
#   Dockerfile EXPOSE, docker-compose port mapping, CI workflow
#   health probes + speech sample test, .env.example `PORT` and
#   `NODE_PORT`, docs/backends.md examples, `tests/bench_160x40w.py`
#   default URL, `setup.sh` post-install hint. Migration for
#   deployments on the old default: set `PORT=5100` in env to keep
#   the legacy endpoint, or repoint the Gatekeeper at `:9004`.
# - 2.2.1 (2026-04-18): /health `model` field now reports the actual
#   model the active backend is running, not the stale `TTS_MODEL`
#   env var. v2.2.0 showed `tts_models/multilingual/multi-dataset/xtts_v2`
#   (the Coqui default) even when `TTS_BACKEND=voxcpm` was active and
#   the loaded model was `openbmb/VoxCPM2`. Added a `model_id()` method
#   to the `TTSBackend` base with per-backend overrides (coqui returns
#   its `_model_name`, voxcpm returns its `_model_id`). Cosmetic only
#   — no behavioural change. Falls back to `TTS_MODEL` if the backend
#   doesn't provide a concrete id.
# - 2.2.0 (2026-04-18): OpenAI-compat polish sweep. One CRITICAL bug
#   (adhoc voice cloning silently broken) plus a cluster of validation
#   gaps surfaced by the full endpoint validation run.
#
#   1. [CRITICAL] Adhoc voice cloning (`custom_voice_file` /
#      `speaker_wav`) was silently disabled. `fastapi.UploadFile` and
#      `starlette.datastructures.UploadFile` are DIFFERENT classes in
#      FastAPI 0.136+ / Starlette 1.0+ (they were aliases in older
#      versions). The handler's `isinstance(custom_file, UploadFile)`
#      check used the fastapi flavour but `form.get()` returns the
#      starlette one — isinstance always returned False, so every
#      "cloning" request silently fell through to the default voice.
#      Responses carried `X-Route: HOT` / `X-Cache: MISS`, with no
#      indication the upload had been dropped. Same root-cause bug as
#      we just fixed in `uttera-tts-vllm` v1.2.0. Fixed by accepting
#      either class (or any file-like object with `read` + `filename`).
#   2. Unknown `voice` silently fell back to the default voice
#      (`DEFAULT_VOICE` / "alloy") without any error. A client asking
#      for "foobar" got alloy audio back with 200 OK. Now rejects with
#      HTTP 400 and the list of available voices.
#   3. `response_format` outside {mp3, wav, pcm, opus, flac} reached
#      ffmpeg and produced HTTP 500 "Audio conversion to yaml failed".
#      Now validated up-front → HTTP 422.
#   4. `speed` outside `[0.25, 4.0]` (OpenAI spec) was not validated.
#      `speed=99` produced HTTP 500 (ffmpeg overflow) and `speed=-1`
#      returned HTTP 200 with garbage audio. Now HTTP 422.
#   5. `temperature` outside `[0.0, 2.0]` (safe Coqui range) was not
#      validated; `temperature=99` returned 200 with garbage. Now 422.
#   6. `cfg_value` outside `[0.5, 5.0]` (VoxCPM safe range) was not
#      validated. Now 422 when explicitly set.
#   7. JSON body without `input` raised `pydantic.ValidationError`
#      that escaped as HTTP 500. Now caught → HTTP 422.
#   8. Bogus / empty `custom_voice_file` silently fell back to the
#      default voice (same root cause as (1), but would also silently
#      accept non-audio bodies with a real UploadFile). Now pre-checks
#      the uploaded file has bytes and a plausible audio extension,
#      and lets the backend decoder surface format errors as HTTP 400.
#   9. HEAD /health returned HTTP 405. Now accepts both GET and HEAD
#      via `@app.api_route(methods=["GET", "HEAD"])`.
#  10. `/v1/models` `owned_by` was still a stale pre-rebrand value.
#      Now `"uttera"`.
#  11. No CORS middleware. Added opt-in `CORSMiddleware` gated on
#      `CORS_ALLOW_ORIGINS` env var (comma-separated or `"*"`).
#      Disabled by default — API-first deployments don't need it.
#  12. Adhoc voice cloning now sets `X-Cache: ADHOC` and bypasses the
#      MD5 audio cache (both read and write). Previously the cache
#      key used the md5 of the temp-file path, so every adhoc request
#      wrote a junk cache entry that could never be re-used — cache
#      pollution. Now symmetric with uttera-tts-vllm v1.2.0.
#  Also: header comment was stuck at `# Version: 2.0.0` since v2.0.0
#  (runtime SERVER_VERSION was already tracking). Resynced to match.
# - 2.1.0 (2026-04-17): Adhoc voice-cloning field additively renamed for
#   symmetry with uttera-tts-vllm v1.1.0. The canonical name is now
#   `custom_voice_file` (unchanged from this server's previous contract);
#   the vllm-native `speaker_wav` is accepted as an alias so the same
#   client code works against either backend. If both are sent on the
#   same request, the canonical one wins. No behavioural change to any
#   existing client — only an additional accepted field name.
# - 2.0.3 (2026-04-17): JSON-body cache opt-out. Clients can now send
#   {"cache": false} (JSON) or cache=0/false/no/off (form) to skip the
#   audio cache for that single request. Symmetric with the existing
#   Cache-Control header support and with uttera-tts-vllm v0.1.4.
# - 2.0.2 (2026-04-17): Per-request cache bypass via Cache-Control
#   HTTP header + response header X-Cache: HIT/MISS/BYPASS/DISABLED.
#   New COLD_VRAM_HEADROOM_GB (default 2.0) reserved on top of the
#   projected cold-pool consumption in _has_vram_for_cold_lane to
#   prevent cascading OOMs with big backends (VoxCPM2 at ~8 GB per
#   cold worker on a 32 GB card).
# - 2.0.1 (2026-04-17): CACHE_TTL_MINUTES=0 now truly disables the
#   cache (previously served every hit regardless of age and kept
#   populating on-disk entries — silent bug surfaced by benchmark
#   runs against small fixed corpora).
# - 2.0.0 (2026-04-16): First Uttera-branded release. BREAKING:
#   * Plugin-based backend architecture. Inference now goes through
#     backends.TTSBackend (ABC) + factory keyed on TTS_BACKEND env var.
#     Default "coqui" — existing deployments unchanged. Coqui-specific code
#     moved to backends/coqui_backend.py; cold_worker_tts.py also wired
#     through the factory so VoxCPM cold pools work.
#   * New VoxCPM2 backend (backends/voxcpm_backend.py) — select with
#     TTS_BACKEND=voxcpm. Personality params (temperature, cfg_value,
#     inference_timesteps) exposed in API schema.
#   * Requirements split per backend: requirements-coqui.txt,
#     requirements-voxcpm.txt. setup.sh accepts a backend arg; Docker
#     builds accept --build-arg TTS_BACKEND.
#   * Rebranded from the pre-rebrand "Coqui TTS Server" to Uttera. Repo moved
#     to github.com/uttera/uttera-tts-hotcold. License set to Apache-2.0.
#   Added: CI workflow (lint + structure + optional GPU smoke),
#     bench_160x40w.py + 40-word prompt corpus + 160 WAV references,
#     docs/backends.md for plugin authors.
#   Fixed: /v1/audio/speech/stream returned empty body — streaming WAV
#     header overflowed uint32 (0xFFFFFFFF + 36) and aborted the generator
#     before any bytes reached the client. Now uses 0xFFFFFFFF directly for
#     both riff_size and data_size (RIFF "unknown length" sentinel).
#   Fixed: Coqui cold worker prints now go to stderr so they don't corrupt
#     the stdout JSON IPC protocol.
#   Fixed: VoxCPM model class name (VoxCPMModel, not VoxCPM2Model).
# - 1.7.1 (2026-04-11): DEFAULT_VOICE env var for configuring the default
#   voice without editing voices.json. Falls back to "alloy" if unset or
#   absent from the voice map.
# - 1.7.0 (2026-04-10): External voice map + precision control + dependency pins.
#   Voice mapping: VOICE_MAP is now loaded from voices.json at startup instead
#   of being hardcoded. Format: {"name": "subdir/file.wav"}. Search order:
#   VOICE_ASSET_DIR/voices.json, then BASE_DIR/voices.json (repo root).
#   Falls back to {"alloy": "standard/alloy.wav"} if neither exists.
#   Precision: new COQUI_PRECISION env var (fp32|fp16|bf16) replaces COQUI_FP16.
#   Legacy COQUI_FP16=1 still works (maps to fp16). bf16 converts model weights
#   to bfloat16 (except HiFiGAN vocoder which needs fp32 for cuFFT) and uses
#   torch.autocast for inference. Monkey-patches torch.Tensor.numpy to handle
#   bf16→fp32 conversion (numpy has no bf16 dtype). Default is fp32.
#   Health endpoint: "fp16" field replaced by "precision" (string).
#   Dependencies: torch pinned to >=2.9.0,<2.10.0 (torch 2.10+ switches
#   torchaudio to torchcodec backend requiring CUDA 13 NPP not yet widely
#   available). torchaudio and torchcodec pinned to matching ranges.
# - 1.6.4 (2026-04-10): Redis self-registration. Each tick of _cold_pool_manager
#   publishes {load_score, accepts_requests, host, port, version, ts} to
#   tts:nodes:{NODE_ID} with TTL=3×interval. Opt-in via REDIS_URL env var;
#   silently disabled if unset or unreachable. Key deleted on clean shutdown.
#   Adds redis[asyncio]>=5.0.0 to requirements.txt.
# - 1.6.3 (2026-04-10): Add routing.load_score and routing.accepts_requests to
#   /health for front-end router support. load_score is drain_estimate/cap (0–1),
#   accepts_requests is False when model not loaded, errored, or score=1.0.
#   ROUTING_DRAIN_CAP_SECONDS env var (default 120) controls saturation threshold.
# - 1.6.2 (2026-04-10): Align /health schema with whisper-stt-local-server.
#   Renamed cold_pool_size→pool_workers_active, cold_pool_loading→pool_workers_loading.
#   Added queue_depth, queue_drain_estimate_seconds, pool_workers_optimal,
#   pool_size_cap, vram_sufficient_for_cold.
# - 1.6.1 (2026-04-09): Fix retried items bouncing between cold pool workers.
#   Cold workers now skip items with retried=True (put back on queue) so only
#   the hot worker processes them, preventing multi-cold-retry loops.
#   Also: reject empty/whitespace-only input with HTTP 422 instead of letting
#   it reach synthesizer.tts() which raises UnboundLocalError on empty text.
# - 1.6.0 (2026-04-09): Shared work queue + persistent cold worker pool. Replaces the
#   Branch A/B/C spawn-and-die architecture (v1.5.x) with a persistent pool of XTTS-v2
#   subprocesses that serve multiple requests without reloading the model (~30 s saved
#   per request after the first). All synthesis requests enqueue to a single asyncio.Queue
#   consumed by the hot worker and all pool workers in parallel. Pool size is computed
#   dynamically every 0.5 s via _optimal_cold_workers() using the live queue depth (words)
#   and EMAs. Idle workers wind down with staggered timeouts (first spawned lives longest).
#   Cold EMA warmup at startup: a real synthesis runs through a fresh cold worker to measure
#   startup time and VRAM cost, then kills the worker before entering steady state.
#   Added COQUI_FP16 option: fp16+LN-fp32 halves VRAM per worker (~3.5→~1.75 GB).
#   (Superseded by COQUI_PRECISION in v1.7.0; COQUI_FP16=1 still works.)
#   Crash fallback preserved: failed pool worker re-queues item to hot lane (X-Route:
#   COLD-POOL>HOT). Zero HTTP 500 from worker crashes.
# - 1.5.7 (2026-04-07): Added cold lane WAV-missing diagnostic; cold_workers_in_flight
#   in /health. Validated 40-clip Spanish stress test: 40/40 OK vs 13/40 in v1.4.10.
# - 1.5.6 (2026-04-06): VRAM pre-check before cold lane dispatch.
# - 1.5.5 (2026-04-06): Fixed model_lock deadlock under client timeout.
# - 1.5.4 (2026-04-06): Auto-calibration of cold start time EMA.
# - 1.5.3 (2026-04-06): EMA no longer updated from fallback path.
# - 1.5.2 (2026-04-06): Cold-Lane Fallback to Hot Lane.
# - 1.5.1 (2026-04-06): Startup EMA Warmup.
# - 1.5.0 (2026-04-06): Smart Hot-Lane Routing (Branch A/B/C).
# - 1.4.x: Various stability and feature additions.
# - 1.1.0 (2026-02-28): Hot/Cold concurrency and GIL bypass.
# - 1.0.0 (2025-11-20): Initial production release.
#
# --- Architecture Summary (v2.0.0) ---
#
# * PLUGIN BACKENDS (v2.0.0)
#   Inference is delegated to a backend implementing backends.TTSBackend.
#   The backend is selected at startup via the TTS_BACKEND env var
#   (default: "coqui"). Built-in options: "coqui" (XTTS-v2, streaming
#   supported) and "voxcpm" (VoxCPM2). See backends/ and docs/backends.md
#   to add a new engine. cold_worker_tts.py uses the same factory, so
#   persistent cold pools work for any backend transparently.
#
# * SHARED WORK QUEUE
#   All synthesis requests (speech endpoint) enqueue a _WorkItem into _work_queue.
#   The hot worker and all pool workers compete for items from the same queue,
#   so pool workers that come online mid-burst immediately start serving already-
#   queued requests — not just new arrivals.
#
# * HOT WORKER LOOP (_hot_worker_loop)
#   Single asyncio Task that consumes _WorkItem entries from _work_queue via
#   asyncio.to_thread(_run_tts_hot_locked). model_lock serializes access so the
#   streaming endpoint can also acquire it safely.
#
# * POOL WORKER LOOP (_pool_worker_loop)
#   One asyncio Task per cold worker. Consumes from the same _work_queue.
#   On failure the item is re-queued for the hot worker (route: COLD-POOL>HOT).
#   Staggered idle timeouts prevent simultaneous mass die-off after a burst.
#
# * DYNAMIC POOL SIZING (_optimal_cold_workers)
#   Formula: N*(N-1) < 2 * queue_work_s / cold_ema
#   where queue_work_s = _work_queue_words * _hot_ema_spw
#   Computed every COLD_POOL_MANAGER_INTERVAL seconds by _cold_pool_manager.
#   Capped by COLD_POOL_SIZE (safety) and VRAM availability.
#
# * STREAM LANE
#   POST /v1/audio/speech/stream uses the backend's infer_stream() on the
#   hot worker (only backends with supports_streaming=True accept this).
#   Acquires model_lock directly; returns HTTP 503 if busy.
#

import os
import time
import uuid
import shutil
import asyncio
import hashlib
import tempfile
import threading
import dataclasses
import warnings
import json
import base64
import subprocess
from contextlib import asynccontextmanager
from typing import Optional, Set
from dotenv import load_dotenv
import redis.asyncio as aioredis

# Load .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for _env_path in [os.path.join(BASE_DIR, ".env"), os.path.join(os.path.dirname(BASE_DIR), ".env")]:
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
        break

warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")
warnings.filterwarnings("ignore", message=".*_register_pytree_node.*")

# Monkey-patch: inject isin_mps_friendly if missing from transformers.
try:
    from transformers.pytorch_utils import isin_mps_friendly  # noqa: F401
except ImportError:
    import torch as _torch
    import transformers.pytorch_utils as _tpu
    def _isin_mps_friendly(elements, test_elements):
        return _torch.isin(elements, test_elements)
    _tpu.isin_mps_friendly = _isin_mps_friendly

# The imports below sit intentionally after the transformers monkey-patch
# above, so noqa: E402 is expected.
from fastapi import FastAPI, UploadFile, HTTPException, Request, BackgroundTasks, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from prometheus_client import (  # noqa: E402
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from pydantic import BaseModel, ValidationError  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from starlette.datastructures import UploadFile as StarletteUploadFile  # noqa: E402
import torch  # noqa: E402

# Plugin-based TTS backends — TTS_BACKEND env var selects the implementation
# (default "coqui"). See backends/__init__.py and backends/base.py.
from backends import load_backend, TTSBackend  # noqa: E402

# Monkey-patch: numpy() does not support bf16; auto-convert to fp32.
_orig_numpy = torch.Tensor.numpy
def _bf16_safe_numpy(self, *args, **kwargs):
    if self.dtype == torch.bfloat16:
        return _orig_numpy(self.float(), *args, **kwargs)
    return _orig_numpy(self, *args, **kwargs)
torch.Tensor.numpy = _bf16_safe_numpy

# -------------------------------
# 1. Global Config
# -------------------------------
PARENT_DIR = os.path.dirname(BASE_DIR)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

def find_venv_path(rel_path):
    local = os.path.join(BASE_DIR, rel_path)
    parent = os.path.join(PARENT_DIR, rel_path)
    if os.path.exists(local):
        return local
    if os.path.exists(parent):
        return parent
    return local

VENV_PYTHON = os.environ.get("VENV_PYTHON", find_venv_path("venv/bin/python"))
COLD_WORKER_TTS_SCRIPT = os.path.join(BASE_DIR, "cold_worker_tts.py")

MODEL_NAME = os.environ.get("TTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")

AUDIO_CACHE_DIR = os.environ.get("AUDIO_CACHE_DIR", os.path.join(ASSETS_DIR, "cache"))
MODEL_CACHE_DIR = os.environ.get("TTS_HOME", os.path.join(ASSETS_DIR, "models"))
VOICE_ASSET_DIR = os.environ.get("VOICE_ASSET_DIR", os.path.join(ASSETS_DIR, "voices"))

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
os.makedirs(VOICE_ASSET_DIR, exist_ok=True)

DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

CACHE_TTL_MINUTES = int(os.environ.get("CACHE_TTL_MINUTES", 10080))

# Precision for hot and cold workers. bf16/fp16 halve VRAM: ~3.5 GB → ~1.75 GB per worker.
# COQUI_PRECISION: "fp32" | "fp16" | "bf16"  (bf16 recommended: same VRAM savings, no overflow risk)
# Legacy COQUI_FP16=1 maps to fp16 for backward compatibility.
_prec_env = os.environ.get("COQUI_PRECISION", "").lower().strip()
if not _prec_env:
    _fp16_env = os.environ.get("COQUI_FP16", "0").lower()
    _prec_env = "fp16" if _fp16_env in ("1", "true", "yes") else "fp32"
if _prec_env not in ("fp32", "fp16", "bf16"):
    raise ValueError(f"COQUI_PRECISION must be fp32, fp16, or bf16 (got '{_prec_env}')")
COQUI_PRECISION = _prec_env
COQUI_FP16 = _prec_env == "fp16"  # legacy compat for env forwarding

# Cold pool sizing (safety cap — actual size is computed dynamically).
COLD_POOL_SIZE = int(os.environ.get("COLD_POOL_SIZE", "6"))

# Idle timeout for cold workers (base value). First-spawned workers live longer
# due to stagger: timeout = COLD_WORKER_IDLE_TIMEOUT + (COLD_POOL_SIZE - n_active) * STAGGER.
COLD_WORKER_IDLE_TIMEOUT = int(os.environ.get("COLD_WORKER_IDLE_TIMEOUT", "60"))
COLD_WORKER_IDLE_STAGGER = int(os.environ.get("COLD_WORKER_IDLE_STAGGER", "10"))

# How often the pool manager wakes to check whether to spawn a new worker.
COLD_POOL_MANAGER_INTERVAL = float(os.environ.get("COLD_POOL_MANAGER_INTERVAL", "0.5"))

# Safety margin: only spawn a cold worker if it would be ready before the queue
# would drain at the current EMA rate, with this factor applied.
HOT_QUEUE_SAFETY_FACTOR = float(os.environ.get("HOT_QUEUE_SAFETY_FACTOR", "0.8"))

# Minimum free VRAM (GB) to spawn a cold worker. 0 = disable check.
MIN_COLD_VRAM_GB = float(os.environ.get("MIN_COLD_VRAM_GB", "2.5"))
# Extra VRAM reserved on top of what the controller projects the cold pool to
# consume. Leaves room for CUDA scratch / temporary activation tensors that the
# workers allocate *during* inference (diffusion attention KV, vocoder, etc.).
# Without this the gate can greenlight a spawn that puts free-VRAM at ~0 and
# crash the next inference inside one of the existing workers. Bigger models
# (VoxCPM2 at ~8 GB each) need more headroom than small ones (Coqui XTTS at
# ~2.5 GB); scale via env if a backend ever needs to override.
COLD_VRAM_HEADROOM_GB = float(os.environ.get("COLD_VRAM_HEADROOM_GB", "2.0"))

# Drain time (seconds) considered 100% load for routing score. Requests with a
# drain estimate at or above this cap receive load_score=1.0 and the node is
# excluded from routing until the queue clears.
ROUTING_DRAIN_CAP_SECONDS = float(os.environ.get("ROUTING_DRAIN_CAP_SECONDS", "120"))

# Redis self-registration (opt-in). If REDIS_URL is unset, publishing is skipped.
# NODE_ID defaults to HOST:PORT. TTL is set to 3× the pool manager interval so
# the key expires automatically if the node dies or Redis becomes unreachable.
REDIS_URL     = os.environ.get("REDIS_URL", "")
REDIS_NODE_ID = os.environ.get("NODE_ID", "") or f"{os.environ.get('NODE_HOST', 'localhost')}:{os.environ.get('NODE_PORT', '9004')}"
REDIS_NODE_HOST = os.environ.get("NODE_HOST", "localhost")
REDIS_NODE_PORT = int(os.environ.get("NODE_PORT", "9004"))
REDIS_KEY     = f"tts:nodes:{REDIS_NODE_ID}"
REDIS_TTL     = max(2, int(COLD_POOL_MANAGER_INTERVAL * 3 + 1))  # seconds

SERVER_VERSION = "2.4.2"

# Response-format whitelist. Anything outside this set is rejected up-front
# at the wrapper instead of blowing up inside ffmpeg with a 500.
SUPPORTED_RESPONSE_FORMATS = {"mp3", "wav", "pcm", "opus", "flac"}

# Validation ranges applied at the wrapper layer. The engines (Coqui /
# VoxCPM2) happily accept out-of-range values and produce garbage; the
# wrapper enforces the OpenAI contract and returns HTTP 422 early.
SPEED_MIN = 0.25            # OpenAI spec lower bound
SPEED_MAX = 4.0             # OpenAI spec upper bound
TEMPERATURE_MIN = 0.0       # Coqui token sampling
TEMPERATURE_MAX = 2.0       # Above ~2 the AR head frequently produces garbage
CFG_MIN = 0.5               # VoxCPM2 classifier-free guidance
CFG_MAX = 5.0               # Above 5 the diffusion solver degenerates to NaN

# -------------------------------
# 2. Voice Mapping — loaded from VOICE_ASSET_DIR/voices.json
# -------------------------------
_voices_json = None
for _candidate in [
    os.path.join(VOICE_ASSET_DIR, "voices.json"),
    os.path.join(BASE_DIR, "voices.json"),
]:
    if os.path.exists(_candidate):
        _voices_json = _candidate
        break

if _voices_json:
    with open(_voices_json) as _f:
        VOICE_MAP = json.load(_f)
    print(f"VOICES: Loaded {len(VOICE_MAP)} voices from {_voices_json}", flush=True)
else:
    VOICE_MAP = {"alloy": "standard/alloy.wav"}
    print("VOICES: No voices.json found — using default (alloy only)", flush=True)

DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "alloy")

# -------------------------------
# 3. OpenAI Schema Models
# -------------------------------
class SpeechRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str = DEFAULT_VOICE
    response_format: str = "mp3"
    speed: float = 1.0
    language: str = os.environ.get("DEFAULT_LANGUAGE", "en")
    # Coqui personality parameters (autoregressive token sampling)
    temperature: float = float(os.environ.get("DEFAULT_TEMPERATURE", 0.75))
    length_penalty: float = float(os.environ.get("DEFAULT_LENGTH_PENALTY", 1.0))
    repetition_penalty: float = float(os.environ.get("DEFAULT_REPETITION_PENALTY", 5.0))
    top_k: int = int(os.environ.get("DEFAULT_TOP_K", 50))
    top_p: float = float(os.environ.get("DEFAULT_TOP_P", 0.85))
    # VoxCPM personality parameters (diffusion)
    # When set, these take priority over Coqui equivalents in the VoxCPM backend.
    # When omitted (None), VoxCPM maps temperature → cfg_value automatically.
    cfg_value: Optional[float] = None
    inference_timesteps: Optional[int] = None
    # Opt out of the server-side audio cache for this specific request. When
    # False the server neither reads nor writes the MD5-keyed audio cache;
    # the response carries `X-Cache: BYPASS`. Omit (None) to fall back to
    # the server default (driven by `CACHE_TTL_MINUTES`).
    cache: Optional[bool] = None

# -------------------------------
# 4. Hot Model Loading (through backend plugin)
# -------------------------------
model_lock = threading.Lock()   # Serializes hot worker + streaming endpoint
_backend: Optional[TTSBackend] = None
hot_worker_error: Optional[str] = None


def _hot_worker_ready() -> bool:
    """True if the backend is loaded and usable."""
    return _backend is not None and hot_worker_error is None


def _load_hot_model():
    """Instantiate and load the configured TTS backend. Called once at startup.

    Backend selection is via the TTS_BACKEND env var (default: coqui).
    Precision (fp32/fp16/bf16) is still controlled by COQUI_PRECISION for
    backward compatibility with existing deployments.
    """
    global _backend, hot_worker_error
    try:
        backend = load_backend()
        print(
            f"HOT WORKER: loading backend '{backend.name}' (precision={COQUI_PRECISION})...",
            flush=True,
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        backend.load(device=device, precision=COQUI_PRECISION)
        _backend = backend
        print("HOT WORKER: Ready.", flush=True)
    except Exception as e:
        hot_worker_error = str(e)
        print(f"HOT WORKER: CRITICAL — failed to load: {e}", flush=True)


_load_hot_model()

# -------------------------------
# 5. EMA Telemetry
# -------------------------------
_HOT_EMA_ALPHA  = 0.2
_COLD_EMA_ALPHA = 0.2

_hot_ema_spw: Optional[float] = None        # seconds per word (hot lane)
_cold_ema_start: Optional[float] = None     # total cold startup + synthesis EMA
_cold_vram_ema_gb: Optional[float] = None   # VRAM per cold worker (measured at warmup)

# Total words currently in the pipeline (queue + being synthesised by hot worker).
_work_queue_words: float = 0.0

# Active pool worker tasks.
_pool_worker_tasks: Set[asyncio.Task] = set()

# Workers currently loading (not yet in _pool_worker_tasks).
_cold_workers_in_flight: int = 0

# Per-cache-key asyncio locks (prevents duplicate synthesis for same text).
_cache_locks: dict = {}

# Shared work queue + spawn lock (initialised in _lifespan).
_work_queue: Optional[asyncio.Queue] = None
_cold_spawn_lock: Optional[asyncio.Lock] = None

# Redis client (None when REDIS_URL is not configured).
_redis: Optional[aioredis.Redis] = None


# -------------------------------
# Prometheus metrics
# -------------------------------
#
# Naming is shared with uttera-tts-vllm (`uttera_tts_*`) so a dashboard
# that aggregates across both backends can use the same queries. The
# `engine` label in uttera_tts_build_info differentiates the variant
# (`coqui` or `voxcpm` for this hotcold backend, `nano-vllm-voxcpm`
# on the sibling). Hot/cold-specific series (queue, cold workers,
# lane routing, VRAM) are additive — they only exist on this server.

# --- HTTP-level (shared shape with sibling vllm backend) ---
_HTTP_REQUESTS_TOTAL = Counter(
    "uttera_tts_requests_total",
    "HTTP requests by endpoint, method and status code",
    ["endpoint", "method", "status"],
)
_HTTP_REQUEST_DURATION = Histogram(
    "uttera_tts_request_duration_seconds",
    "HTTP request wall-clock duration in seconds",
    ["endpoint", "method"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
_INFLIGHT_GAUGE = Gauge(
    "uttera_tts_inflight_requests",
    "Synthesis requests currently in flight (hot + cold lanes combined)",
)
_ENGINE_READY_GAUGE = Gauge(
    "uttera_tts_engine_ready",
    "1 if the hot worker backend is loaded and ready, 0 otherwise",
)
_VOICES_LOADED_GAUGE = Gauge(
    "uttera_tts_voices_loaded",
    "Number of voices registered (entries in voices.json)",
)

# --- Shared synthesis counters (same shape as vllm sibling) ---
_SYNTHESIS_TOTAL = Counter(
    "uttera_tts_synthesis_total",
    "Synthesis requests broken down by output format, lane, and cache decision",
    ["response_format", "route", "cache"],
    # response_format ∈ {mp3, wav, pcm, opus, flac}
    # route           ∈ {HOT, COLD-POOL, COLD-POOL>HOT, CACHE, ADHOC}
    # cache           ∈ {HIT, MISS, BYPASS, ADHOC, DISABLED}
)
_CHARACTERS_SYNTHESISED_TOTAL = Counter(
    "uttera_tts_characters_synthesised_total",
    "Total input characters successfully synthesised (billing / throughput proxy)",
    ["response_format"],
)

# --- Inference-duration histogram (per-op, lane-tagged) ---
# op values:
#   synthesis_hot    — the always-resident hot worker handled it
#   synthesis_cold   — a cold-pool subprocess handled it
#   ffmpeg_encode    — output-format transcoding (mp3/opus/flac)
_INFERENCE_DURATION = Histogram(
    "uttera_tts_inference_duration_seconds",
    "Per-call inference latency in seconds, by op",
    ["op"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

_ERRORS_TOTAL = Counter(
    "uttera_tts_errors_total",
    "Errors by type",
    ["type"],   # decode | validation | model | encoding
)

_BUILD_INFO = Gauge(
    "uttera_tts_build_info",
    "Build metadata (label values carry version, engine and served model id)",
    ["version", "engine", "model"],
)

# --- Hot/cold pool specific (additive vs the vllm sibling) ---
_REQUESTS_BY_ROUTE_TOTAL = Counter(
    "uttera_tts_requests_by_route_total",
    "Successful synthesis requests broken down by which lane ultimately served them",
    ["route"],   # HOT | COLD-POOL | COLD-POOL>HOT | CACHE | ADHOC
)
_COLD_WORKERS_ACTIVE_GAUGE = Gauge(
    "uttera_tts_cold_workers_active",
    "Cold worker subprocesses currently alive and consuming from the work queue",
)
_COLD_WORKERS_LOADING_GAUGE = Gauge(
    "uttera_tts_cold_workers_loading",
    "Cold worker subprocesses currently in their spawn/load phase",
)
_COLD_WORKER_POOL_CAP_GAUGE = Gauge(
    "uttera_tts_cold_worker_pool_size_cap",
    "Configured COLD_POOL_SIZE — ceiling on active + loading cold workers",
)
_COLD_WORKERS_SPAWNED_TOTAL = Counter(
    "uttera_tts_cold_workers_spawned_total",
    "Total cold worker subprocesses ever successfully spawned (monotonic)",
)
_COLD_EMA_START_GAUGE = Gauge(
    "uttera_tts_cold_worker_ema_start_seconds",
    "Rolling EMA of cold worker boot time (seconds from spawn to first-serve)",
)
_WORK_QUEUE_DEPTH_GAUGE = Gauge(
    "uttera_tts_work_queue_depth",
    "Items currently queued waiting for a hot or cold worker",
)
_WORK_QUEUE_WORDS_GAUGE = Gauge(
    "uttera_tts_work_queue_words",
    "Sum of input-text word counts waiting in the work queue (drain-estimate input)",
)
_LOAD_SCORE_GAUGE = Gauge(
    "uttera_tts_load_score",
    "Current load score in [0.0, 1.0]; 1.0 means the queue would take ROUTING_DRAIN_CAP_SECONDS or more to drain",
)
_HOT_EMA_SPW_GAUGE = Gauge(
    "uttera_tts_hot_ema_spw",
    "Rolling EMA of the hot worker's seconds per word (lower = faster)",
)
_VRAM_FREE_GB_GAUGE = Gauge(
    "uttera_tts_vram_free_gb",
    "Free VRAM on the serving GPU in GB",
)
_VRAM_PER_COLD_WORKER_GB_GAUGE = Gauge(
    "uttera_tts_vram_per_cold_worker_gb",
    "Rolling EMA of VRAM consumed by each cold worker subprocess, in GB",
)

_KNOWN_ENDPOINTS = {
    "/v1/audio/speech",
    "/v1/audio/speech/stream",
    "/v1/voices",
    "/admin/reload-voices",
    "/v1/models",
    "/health",
    "/metrics",
}


async def _publish_to_redis(load_score: float, accepts: bool) -> None:
    """Publish this node's routing state to Redis. Fails silently if unavailable."""
    if _redis is None:
        return
    try:
        payload = json.dumps({
            "load_score":       load_score,
            "accepts_requests": accepts,
            "host":             REDIS_NODE_HOST,
            "port":             REDIS_NODE_PORT,
            "version":          SERVER_VERSION,
            "ts":               time.time(),
        })
        await _redis.set(REDIS_KEY, payload, ex=REDIS_TTL)
    except Exception:
        pass  # Redis unavailability must never affect request serving


def _count_words(text: str) -> int:
    return max(1, len(text.split()))


def _update_hot_ema(elapsed: float, word_count: int) -> None:
    global _hot_ema_spw
    spw = elapsed / word_count
    _hot_ema_spw = spw if _hot_ema_spw is None else (_HOT_EMA_ALPHA * spw + (1 - _HOT_EMA_ALPHA) * _hot_ema_spw)


def _update_cold_ema(elapsed: float) -> None:
    global _cold_ema_start
    _cold_ema_start = elapsed if _cold_ema_start is None else (_COLD_EMA_ALPHA * elapsed + (1 - _COLD_EMA_ALPHA) * _cold_ema_start)


def _update_cold_vram_ema(drop_gb: float) -> None:
    global _cold_vram_ema_gb
    _cold_vram_ema_gb = drop_gb if _cold_vram_ema_gb is None else (0.2 * drop_gb + 0.8 * _cold_vram_ema_gb)


def _get_cold_start_time() -> float:
    return _cold_ema_start if _cold_ema_start is not None else 30.0


def _free_vram_gb() -> Optional[float]:
    if not torch.cuda.is_available():
        return None
    free_bytes, _ = torch.cuda.mem_get_info()
    return free_bytes / (1024 ** 3)


def _has_vram_for_cold_lane() -> bool:
    threshold = _cold_vram_ema_gb if _cold_vram_ema_gb is not None else MIN_COLD_VRAM_GB
    if threshold <= 0:
        return True
    free = _free_vram_gb()
    if free is None:
        return True
    effective = free - (_cold_workers_in_flight * threshold) - COLD_VRAM_HEADROOM_GB
    return effective >= threshold


# -------------------------------
# 6. Work Item
# -------------------------------
@dataclasses.dataclass
class _WorkItem:
    text: str
    speaker_wav: str
    language: str
    speed: float
    params: dict
    word_count: int
    future: asyncio.Future
    route: str = dataclasses.field(default="HOT")
    retried: bool = dataclasses.field(default=False)

# -------------------------------
# 7. Cold Worker Subprocess
# -------------------------------
class _ColdTTSWorker:
    """Manages a single persistent cold_worker_tts.py subprocess."""

    def __init__(self):
        self._proc: Optional[asyncio.subprocess.Process] = None

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def _read_stderr(self) -> str:
        """Read and return any pending stderr output from the subprocess (for diagnostics)."""
        if self._proc is None or self._proc.stderr is None:
            return ""
        try:
            data = await asyncio.wait_for(self._proc.stderr.read(65536), timeout=2.0)
            return data.decode(errors="replace").strip()
        except Exception:
            return ""

    async def spawn(self) -> bool:
        """Spawn the subprocess and wait for {"ready": true}. Returns False on failure."""
        env = os.environ.copy()
        # Forward backend selection to the cold worker subprocess so it
        # instantiates the same plugin as the hot worker.
        env["TTS_BACKEND"]              = (_backend.name if _backend is not None
                                           else os.environ.get("TTS_BACKEND", "coqui"))
        env["TTS_MODEL"]                = MODEL_NAME
        env["TTS_HOME"]                 = MODEL_CACHE_DIR
        env["COQUI_PRECISION"]           = COQUI_PRECISION
        env["COLD_WORKER_IDLE_TIMEOUT"] = str(COLD_WORKER_IDLE_TIMEOUT)
        env["COQUI_TOS_AGREED"]         = "1"
        try:
            self._proc = await asyncio.create_subprocess_exec(
                VENV_PYTHON, COLD_WORKER_TTS_SCRIPT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                limit=10 * 1024 * 1024,  # 10 MB — XTTS-v2 audio responses can exceed 1 MB base64
            )
            # Wait for {"ready": true}
            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=120.0)
            msg = json.loads(line.strip())
            return bool(msg.get("ready"))
        except Exception as e:
            stderr_out = await self._read_stderr()
            if stderr_out:
                print(f"COLD WORKER: spawn stderr:\n{stderr_out}", flush=True)
            print(f"COLD WORKER: spawn failed: {e}", flush=True)
            await self.shutdown()
            return False

    async def synthesize(self, text: str, speaker_wav: str, language: str,
                         speed: float, params: dict) -> bytes:
        """Send one request, return raw WAV bytes. Raises on error."""
        req = {
            "text": text,
            "speaker_wav": speaker_wav,
            "language": language,
            "speed": speed,
            **params,
        }
        line_bytes = (json.dumps(req) + "\n").encode()
        self._proc.stdin.write(line_bytes)
        await self._proc.stdin.drain()

        try:
            response_line = await self._proc.stdout.readline()
            resp = json.loads(response_line.strip())
        except Exception:
            stderr_out = await self._read_stderr()
            if stderr_out:
                print(f"COLD WORKER: subprocess stderr:\n{stderr_out}", flush=True)
            raise
        if "error" in resp:
            stderr_out = await self._read_stderr()
            if stderr_out:
                print(f"COLD WORKER: subprocess stderr:\n{stderr_out}", flush=True)
            raise RuntimeError(resp["error"])
        return base64.b64decode(resp["audio_b64"])

    async def shutdown(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.returncode is None:
                self._proc.stdin.write(b'{"exit": true}\n')
                await self._proc.stdin.drain()
                self._proc.stdin.close()
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

# -------------------------------
# 8. Pool Management
# -------------------------------
def _optimal_cold_workers() -> int:
    """
    Compute optimal cold pool size given current queue depth and EMAs.

    Finds the largest N where the last cold worker finishes loading before
    the burst is done: N*(N-1) < 2 * queue_work_s / cold_ema
    where queue_work_s = _work_queue_words * _hot_ema_spw
    """
    if _hot_ema_spw is None or _work_queue_words <= 0:
        return 0
    cold_start = _get_cold_start_time()
    if cold_start <= 0:
        return 0
    total_work_s = _work_queue_words * _hot_ema_spw
    limit = 2.0 * total_work_s / cold_start
    N_total = 1
    while N_total * (N_total - 1) < limit:
        N_total += 1
    N_total -= 1
    cold = N_total - 1
    if COLD_POOL_SIZE > 0:
        cold = min(cold, COLD_POOL_SIZE)
    return max(0, cold)


async def _spawn_cold_worker() -> _ColdTTSWorker:
    """Spawn one cold worker, tracking in-flight count and VRAM."""
    global _cold_workers_in_flight
    _cold_workers_in_flight += 1
    v_before = _free_vram_gb() or 0.0
    worker = _ColdTTSWorker()
    try:
        ok = await worker.spawn()
        if not ok:
            raise RuntimeError("Cold worker failed to become ready")
        v_after = _free_vram_gb() or 0.0
        drop = v_before - v_after
        if drop > 0.1:
            _update_cold_vram_ema(drop)
        return worker
    finally:
        _cold_workers_in_flight -= 1

# -------------------------------
# 9. Worker Loops
# -------------------------------
def _run_tts_hot_locked(text: str, lang: str, speaker_wav: str,
                         speed: float, output_path: str, params: dict):
    """Acquire model_lock, synthesize, release — all in one thread (deadlock-safe)."""
    model_lock.acquire()
    try:
        _run_tts_hot_lane(text, lang, speaker_wav, speed, output_path, params)
    finally:
        model_lock.release()


def _run_tts_hot_lane(text: str, lang: str, speaker_wav: str,
                       speed: float, output_path: str, params: dict):
    """Synthesize `text` through the hot backend and write the WAV to disk.

    Backend-specific concerns (autocast, model internals) are encapsulated
    inside `_backend.infer()`. This function just bridges the server's
    file-based contract with the backend's bytes-returning API.
    """
    wav_bytes = _backend.infer(
        text=text,
        voice_wav_path=speaker_wav,
        language=lang,
        speed=speed,
        params=params,
    )
    with open(output_path, "wb") as f:
        f.write(wav_bytes)


async def _hot_worker_loop() -> None:
    """Persistent asyncio Task consuming _WorkItem entries from _work_queue (hot lane)."""
    global _work_queue_words
    while True:
        try:
            item: _WorkItem = await _work_queue.get()
        except asyncio.CancelledError:
            break

        if item.retried:
            item.route = "COLD-POOL>HOT"
        else:
            item.route = "HOT"

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                temp_path = f.name
            t0 = time.monotonic()
            await asyncio.to_thread(
                _run_tts_hot_locked,
                item.text, item.language, item.speaker_wav,
                item.speed, temp_path, item.params,
            )
            elapsed = time.monotonic() - t0
            _update_hot_ema(elapsed, item.word_count)
            with open(temp_path, "rb") as f:
                audio_bytes = f.read()
            if not item.future.done():
                item.future.set_result((audio_bytes, item.route))
        except asyncio.CancelledError:
            if not item.future.done():
                item.future.cancel()
            raise
        except Exception as e:
            if not item.future.done():
                item.future.set_exception(e)
        finally:
            _work_queue_words -= item.word_count
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)


async def _pool_worker_loop(worker: _ColdTTSWorker, idle_timeout: float) -> None:
    """
    Persistent asyncio Task for one cold pool worker.
    Consumes _WorkItem entries from the same _work_queue as the hot worker.
    Staggered idle_timeout set at spawn time prevents simultaneous mass die-off.
    """
    global _work_queue_words
    try:
        while True:
            try:
                item: _WorkItem = await asyncio.wait_for(
                    _work_queue.get(), timeout=idle_timeout
                )
            except asyncio.TimeoutError:
                print(f"--- POOL WORKER: idle timeout ({idle_timeout:.0f}s), exiting ---", flush=True)
                break
            except asyncio.CancelledError:
                break

            # Retried items are reserved for the hot worker — put back and skip.
            if item.retried:
                await _work_queue.put(item)
                continue

            item.route = "COLD-POOL"
            requeued = False
            try:
                audio_bytes = await worker.synthesize(
                    item.text, item.speaker_wav, item.language,
                    item.speed, item.params,
                )
                if not item.future.done():
                    item.future.set_result((audio_bytes, item.route))
            except asyncio.CancelledError:
                if not item.future.done():
                    item.future.cancel()
                raise
            except Exception as e:
                print(f"--- POOL WORKER: synthesis failed ({e}), re-queuing to hot lane ---", flush=True)
                if not item.future.done():
                    item.retried = True
                    _work_queue_words += item.word_count   # restore before finally decrements
                    await _work_queue.put(item)
                    requeued = True
                if not worker.is_alive():
                    break
            finally:
                if not requeued:
                    _work_queue_words -= item.word_count
    finally:
        await worker.shutdown()


async def _cold_pool_manager() -> None:
    """
    Background task: dynamically spawns cold workers based on current queue depth.
    Wakes every COLD_POOL_MANAGER_INTERVAL seconds. Also publishes routing state
    to Redis on every tick (no-op when REDIS_URL is not configured).
    """
    while True:
        await asyncio.sleep(COLD_POOL_MANAGER_INTERVAL)

        target = _optimal_cold_workers()
        active = len(_pool_worker_tasks)
        loading = _cold_workers_in_flight

        if active + loading < target and _cold_spawn_lock and not _cold_spawn_lock.locked() and _has_vram_for_cold_lane():
            drain_s = _work_queue_words * (_hot_ema_spw or 0)
            print(
                f"--- POOL MGR: target={target} cold workers (active={active}, loading={loading})"
                f" | queue={_work_queue_words:.0f} words ({drain_s:.1f}s drain) → spawning ---",
                flush=True,
            )
            try:
                async with _cold_spawn_lock:
                    worker = await _spawn_cold_worker()
                n_active = len(_pool_worker_tasks)
                stagger = max(0, COLD_POOL_SIZE - n_active) * COLD_WORKER_IDLE_STAGGER
                worker_idle_timeout = float(COLD_WORKER_IDLE_TIMEOUT + stagger)
                task = asyncio.create_task(_pool_worker_loop(worker, worker_idle_timeout))
                _pool_worker_tasks.add(task)
                task.add_done_callback(_pool_worker_tasks.discard)
                _COLD_WORKERS_SPAWNED_TOTAL.inc()
                print(
                    f"--- POOL MGR: pool worker ready, total_active={len(_pool_worker_tasks)}"
                    f", idle_timeout={worker_idle_timeout:.0f}s ---",
                    flush=True,
                )
            except Exception as e:
                print(f"--- POOL MGR: spawn failed: {e} ---", flush=True)

        # Publish routing state to Redis on every tick (no-op if not configured).
        drain = (_work_queue_words * _hot_ema_spw) if _hot_ema_spw else None
        if drain is not None:
            load_score = round(min(drain / ROUTING_DRAIN_CAP_SECONDS, 1.0), 3)
        else:
            load_score = round(min(_work_queue_words / 500.0, 1.0), 3)
        accepts = _hot_worker_ready() and load_score < 1.0
        await _publish_to_redis(load_score, accepts)

# -------------------------------
# 10. Startup Warmup
# -------------------------------
async def _warmup_hot_ema() -> None:
    """Seed _hot_ema_spw via a real synthesis through the hot lane."""
    if not _hot_worker_ready():
        return
    warmup_text = "All systems nominal. Standing by for further orders."
    word_count = _count_words(warmup_text)
    speaker_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP.get("alloy", "standard/alloy.wav"))
    if not os.path.exists(speaker_wav):
        print("WARMUP HOT: Speaker WAV not found. Skipping.", flush=True)
        return
    print("WARMUP HOT: Seeding EMA with synthesis...", flush=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            temp_path = f.name
        params = {"temperature": 0.75, "length_penalty": 1.0, "repetition_penalty": 5.0,
                  "top_k": 50, "top_p": 0.85}
        t0 = time.monotonic()
        await asyncio.to_thread(_run_tts_hot_lane, warmup_text, "en", speaker_wav, 1.0, temp_path, params)
        elapsed = time.monotonic() - t0
        _update_hot_ema(elapsed, word_count)
        print(f"WARMUP HOT: EMA seeded. spw={_hot_ema_spw:.4f} (elapsed={elapsed:.2f}s, {word_count} words)", flush=True)
    except Exception as e:
        print(f"WARMUP HOT: Failed ({e}). Starting in uncalibrated mode.", flush=True)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


async def _warmup_cold_ema() -> None:
    """
    Spawn one cold worker, synthesise, measure total elapsed as cold_ema_start,
    measure VRAM drop, then kill the worker before steady state.
    """
    if COLD_POOL_SIZE <= 0:
        return
    warmup_text = "Cold lane calibration complete."
    speaker_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP.get("alloy", "standard/alloy.wav"))
    if not os.path.exists(speaker_wav):
        print("WARMUP COLD: Speaker WAV not found. Skipping.", flush=True)
        return
    print("WARMUP COLD: Spawning cold worker to calibrate cold_ema...", flush=True)
    global _cold_workers_in_flight
    v_before = _free_vram_gb() or 0.0
    _cold_workers_in_flight += 1
    worker = _ColdTTSWorker()
    t_start = time.monotonic()
    try:
        ok = await worker.spawn()
        if not ok:
            print("WARMUP COLD: Worker failed to start. cold_ema uncalibrated.", flush=True)
            return
        v_after = _free_vram_gb() or 0.0
        drop = v_before - v_after
        if drop > 0.1:
            _update_cold_vram_ema(drop)
        _cold_workers_in_flight -= 1
        params = {"temperature": 0.75, "length_penalty": 1.0, "repetition_penalty": 5.0,
                  "top_k": 50, "top_p": 0.85}
        await worker.synthesize(warmup_text, speaker_wav, "en", 1.0, params)
        total_elapsed = time.monotonic() - t_start
        _update_cold_ema(total_elapsed)
        print(
            f"WARMUP COLD: cold_ema={total_elapsed:.1f}s | "
            f"vram_drop={drop:.2f}GB (EMA={_cold_vram_ema_gb:.2f}GB)",
            flush=True,
        )
    except Exception as e:
        print(f"WARMUP COLD: Failed ({e}). cold_ema uncalibrated.", flush=True)
        if _cold_workers_in_flight > 0:
            _cold_workers_in_flight -= 1
    finally:
        await worker.shutdown()


@asynccontextmanager
async def _lifespan(application: FastAPI):
    global _work_queue, _cold_spawn_lock, _redis

    _work_queue = asyncio.Queue()
    _cold_spawn_lock = asyncio.Lock()

    if REDIS_URL:
        try:
            _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await _redis.ping()
            print(f"Redis connected: {REDIS_URL} | key={REDIS_KEY} ttl={REDIS_TTL}s", flush=True)
        except Exception as e:
            print(f"Redis unavailable ({e}) — running without registration.", flush=True)
            _redis = None

    await _warmup_hot_ema()
    await _warmup_cold_ema()

    hot_task = asyncio.create_task(_hot_worker_loop())
    manager_task = asyncio.create_task(_cold_pool_manager())

    yield

    hot_task.cancel()
    manager_task.cancel()
    for task in list(_pool_worker_tasks):
        task.cancel()
    await asyncio.gather(hot_task, manager_task, *list(_pool_worker_tasks), return_exceptions=True)

    if _redis:
        try:
            await _redis.delete(REDIS_KEY)
        except Exception:
            pass
        await _redis.aclose()


app = FastAPI(title="Uttera TTS Server", version=SERVER_VERSION, lifespan=_lifespan)

# Opt-in CORS middleware. API-first deployments don't need CORS, so it
# stays off by default. Set CORS_ALLOW_ORIGINS to a comma-separated list
# of origins, or "*" to allow all.
_cors_origins_env = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
if _cors_origins_env:
    _cors_origins = ["*"] if _cors_origins_env == "*" else [
        o.strip() for o in _cors_origins_env.split(",") if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "HEAD", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Route", "X-Cache"],
    )


# Prometheus middleware — tracks every HTTP request generically.
# Synthesis-specific labels (response_format, route, cache decision,
# character count) are attached inside the endpoint handlers.

class _PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        method = request.method
        if path == "/metrics":
            return await call_next(request)
        endpoint = path if path in _KNOWN_ENDPOINTS else "other"
        t0 = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.monotonic() - t0
            _HTTP_REQUESTS_TOTAL.labels(
                endpoint=endpoint, method=method, status=str(status)
            ).inc()
            _HTTP_REQUEST_DURATION.labels(
                endpoint=endpoint, method=method
            ).observe(elapsed)

app.add_middleware(_PrometheusMiddleware)

# Static gauges — set once at module import time. Backend selection
# (coqui / voxcpm) becomes the `engine` label so dashboards can
# filter by backend without a secondary lookup.
_BUILD_INFO.labels(
    version=SERVER_VERSION,
    engine=os.environ.get("TTS_BACKEND", "coqui").strip().lower() or "coqui",
    model=os.environ.get("TTS_MODEL", "xtts_v2"),
).set(1)
_COLD_WORKER_POOL_CAP_GAUGE.set(COLD_POOL_SIZE)


# -------------------------------
# 10b. Validation helpers
# -------------------------------
def _is_upload_file(value) -> bool:
    """Return True if `value` is a file-upload object.

    FastAPI 0.100+ and Starlette 1.0+ ship distinct `UploadFile` classes
    (`fastapi.datastructures.UploadFile` vs
    `starlette.datastructures.UploadFile`), and Starlette's form parser
    always returns the Starlette flavour. A plain
    `isinstance(x, fastapi.UploadFile)` check against a Starlette
    instance silently returns False — which is how adhoc voice cloning
    was broken up to v2.1.0. Match both classes explicitly; fall back
    to duck-typing (`read` + `filename`) so any future divergence keeps
    working.
    """
    if isinstance(value, (UploadFile, StarletteUploadFile)):
        return True
    return (
        not isinstance(value, (str, bytes))
        and hasattr(value, "read")
        and hasattr(value, "filename")
    )


def _validate_speech_request(req: "SpeechRequest", available_voices: set) -> None:
    """Wrapper-layer validation that the engines do not police themselves.

    Raises HTTPException with 4xx codes; never returns bad values.
    """
    if req.response_format.lower() not in SUPPORTED_RESPONSE_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"response_format '{req.response_format}' not supported. "
                f"Use one of: {sorted(SUPPORTED_RESPONSE_FORMATS)}"
            ),
        )
    if not (SPEED_MIN <= req.speed <= SPEED_MAX):
        raise HTTPException(
            status_code=422,
            detail=f"speed {req.speed} out of range. Must be in [{SPEED_MIN}, {SPEED_MAX}].",
        )
    if not (TEMPERATURE_MIN <= req.temperature <= TEMPERATURE_MAX):
        raise HTTPException(
            status_code=422,
            detail=f"temperature {req.temperature} out of range. Must be in [{TEMPERATURE_MIN}, {TEMPERATURE_MAX}].",
        )
    if req.cfg_value is not None and not (CFG_MIN <= req.cfg_value <= CFG_MAX):
        raise HTTPException(
            status_code=422,
            detail=f"cfg_value {req.cfg_value} out of range. Must be in [{CFG_MIN}, {CFG_MAX}].",
        )


# -------------------------------
# 11. Audio Utilities
# -------------------------------
def convert_audio(input_path: str, output_path: str, fmt: str):
    if fmt == "wav":
        shutil.copy(input_path, output_path)
        return
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if fmt == "mp3":
        cmd.extend(["-codec:a", "libmp3lame", "-qscale:a", "2"])
    elif fmt == "opus":
        cmd.extend(["-codec:a", "libopus", "-b:a", "64k"])
    elif fmt == "flac":
        cmd.extend(["-codec:a", "flac"])
    cmd.append(output_path)
    try:
        subprocess.run(cmd, capture_output=(not DEBUG), check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] ffmpeg error (code {e.returncode}): {e}", flush=True)
        raise RuntimeError(f"Audio conversion to {fmt} failed (ffmpeg exited {e.returncode})")

# -------------------------------
# 12. Endpoints: /health, /v1/models, /v1/voices
# -------------------------------
@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "tts-1",    "object": "model", "created": 1677610602, "owned_by": "uttera"},
            {"id": "tts-1-hd", "object": "model", "created": 1677610602, "owned_by": "uttera"},
        ],
    }

@app.get("/v1/voices")
async def list_voices():
    return {"voices": sorted(list(VOICE_MAP.keys()))}

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    _free = _free_vram_gb()
    drain = round(_work_queue_words * _hot_ema_spw, 2) if _hot_ema_spw else None
    if drain is not None:
        load_score = round(min(drain / ROUTING_DRAIN_CAP_SECONDS, 1.0), 3)
    else:
        # Not yet calibrated — use word count as rough proxy (500 words ≈ saturated)
        load_score = round(min(_work_queue_words / 500.0, 1.0), 3)
    accepts = _hot_worker_ready() and load_score < 1.0
    # Prefer the backend's `model_id()` over the TTS_MODEL env var so
    # /health reports the concrete model the active backend is running
    # (e.g. openbmb/VoxCPM2 when TTS_BACKEND=voxcpm) rather than the
    # Coqui-default env var.
    backend_model_id = _backend.model_id() if _backend is not None else None
    return {
        "status": "ok",
        "version": SERVER_VERSION,
        "backend": _backend.name if _backend is not None else None,
        "model": backend_model_id or MODEL_NAME,
        "precision": COQUI_PRECISION,
        "hot_worker_loaded": _hot_worker_ready(),
        "hot_worker_error": hot_worker_error,
        "routing": {
            "load_score": load_score,
            "accepts_requests": accepts,
        },
        "smart_routing": {
            "ema_spw": round(_hot_ema_spw, 4) if _hot_ema_spw is not None else None,
            "cold_start_calibrated": _cold_ema_start is not None,
            "cold_ema_start_seconds": round(_cold_ema_start, 2) if _cold_ema_start is not None else None,
            "queue_depth": _work_queue.qsize() if _work_queue is not None else 0,
            "queue_words": _work_queue_words,
            "queue_drain_estimate_seconds": drain,
            "pool_workers_active": len(_pool_worker_tasks),
            "pool_workers_loading": _cold_workers_in_flight,
            "pool_workers_optimal": _optimal_cold_workers(),
            "pool_size_cap": COLD_POOL_SIZE,
            "vram_free_gb": round(_free, 2) if _free is not None else None,
            "cold_vram_ema_gb": round(_cold_vram_ema_gb, 2) if _cold_vram_ema_gb is not None else None,
            "vram_sufficient_for_cold": _has_vram_for_cold_lane(),
        },
    }

# -------------------------------
# 13. Endpoint: POST /v1/audio/speech
# -------------------------------
def _cache_header_bypass(request: Request) -> bool:
    """Honour the standard HTTP `Cache-Control: no-cache` header as an opt-out
    for this specific request, without requiring the operator to set
    `CACHE_TTL_MINUTES=0` globally. Bench harnesses and clients that want
    apples-to-apples throughput measurements use this instead of racing against
    a warmed cache. `no-store` is treated as the same opt-out."""
    cc = request.headers.get("Cache-Control", "").lower()
    return any(tok in cc for tok in ("no-cache", "no-store"))


# -------------------------------
# 11b. /metrics (Prometheus)
# -------------------------------

def _refresh_gauges_from_state() -> None:
    """Snapshot live routing state into Prometheus gauges. Mirrors what
    health_check() already computes — called on every /metrics scrape
    so we don't need to hook every state-change site."""
    _ENGINE_READY_GAUGE.set(1 if _backend is not None else 0)
    _VOICES_LOADED_GAUGE.set(len(VOICE_MAP))
    _COLD_WORKERS_ACTIVE_GAUGE.set(len(_pool_worker_tasks))
    _COLD_WORKERS_LOADING_GAUGE.set(_cold_workers_in_flight)
    _WORK_QUEUE_DEPTH_GAUGE.set(_work_queue.qsize() if _work_queue is not None else 0)
    _WORK_QUEUE_WORDS_GAUGE.set(_work_queue_words)
    if _hot_ema_spw is not None:
        _HOT_EMA_SPW_GAUGE.set(_hot_ema_spw)
        drain = _work_queue_words * _hot_ema_spw
        _LOAD_SCORE_GAUGE.set(min(drain / ROUTING_DRAIN_CAP_SECONDS, 1.0))
    else:
        _LOAD_SCORE_GAUGE.set(min(_work_queue_words / ROUTING_DRAIN_CAP_SECONDS, 1.0))
    if _cold_ema_start is not None:
        _COLD_EMA_START_GAUGE.set(_cold_ema_start)
    _free = _free_vram_gb()
    if _free is not None:
        _VRAM_FREE_GB_GAUGE.set(_free)
    if _cold_vram_ema_gb is not None:
        _VRAM_PER_COLD_WORKER_GB_GAUGE.set(_cold_vram_ema_gb)


@app.get("/metrics")
async def metrics():
    """Prometheus-format scrape endpoint.

    Exposes the shared `uttera_tts_*` HTTP and synthesis metrics
    plus this server's hot/cold-specific pool telemetry (cold
    workers active/loading/spawned, queue depth, VRAM, load score).
    Cardinality is bounded by design — no per-voice labels, no
    per-request-id labels.

    Scrape with Telegraf's `inputs.prometheus`, Prometheus itself,
    or any OpenMetrics-compatible consumer.
    """
    _refresh_gauges_from_state()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/audio/speech")
async def create_speech(request: Request, background_tasks: BackgroundTasks):
    content_type = request.headers.get("Content-Type", "")
    header_bypass = _cache_header_bypass(request)
    custom_wav_path = None
    if "application/json" in content_type:
        data = await request.json()
        try:
            req = SpeechRequest(**data)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())
    else:
        form_data = await request.form()
        _raw_cache = form_data.get("cache")
        _cache_field: Optional[bool] = None
        if _raw_cache is not None:
            _cache_field = str(_raw_cache).strip().lower() not in ("0", "false", "no", "off")
        try:
            req = SpeechRequest(
                input=form_data.get("input"),
                voice=form_data.get("voice", DEFAULT_VOICE),
                response_format=form_data.get("response_format", "mp3"),
                speed=float(form_data.get("speed", 1.0)),
                language=form_data.get("language", os.environ.get("DEFAULT_LANGUAGE", "en")),
                temperature=float(form_data.get("temperature", os.environ.get("DEFAULT_TEMPERATURE", 0.75))),
                length_penalty=float(form_data.get("length_penalty", os.environ.get("DEFAULT_LENGTH_PENALTY", 1.0))),
                repetition_penalty=float(form_data.get("repetition_penalty", os.environ.get("DEFAULT_REPETITION_PENALTY", 5.0))),
                top_k=int(form_data.get("top_k", os.environ.get("DEFAULT_TOP_K", 50))),
                top_p=float(form_data.get("top_p", os.environ.get("DEFAULT_TOP_P", 0.85))),
                cache=_cache_field,
            )
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())
        # Canonical field name is `custom_voice_file`. `speaker_wav` is
        # accepted as an alias for uttera-tts-vllm parity. If both are
        # sent, the canonical one wins. The UploadFile isinstance check
        # accepts both FastAPI's and Starlette's class (they diverged in
        # FastAPI 0.136+ / Starlette 1.0+) — see `_is_upload_file`.
        custom_file = form_data.get("custom_voice_file") or form_data.get("speaker_wav")
        if _is_upload_file(custom_file):
            custom_bytes = await custom_file.read()
            if not custom_bytes:
                raise HTTPException(
                    status_code=400,
                    detail="custom_voice_file is empty — upload a valid audio body.",
                )
            # Preserve the uploader's filename suffix so backends that
            # dispatch on extension (libsndfile / librosa) can decode.
            orig_suffix = os.path.splitext(custom_file.filename or "upload.wav")[1].lower() or ".wav"
            temp_custom = tempfile.NamedTemporaryFile(delete=False, suffix=orig_suffix)
            temp_custom.write(custom_bytes)
            temp_custom.close()
            custom_wav_path = temp_custom.name

    if not req.input or not req.input.strip():
        raise HTTPException(status_code=422, detail="'input' must be a non-empty string.")

    # Wrapper-level validation (OpenAI spec + safe ranges for the engines).
    _validate_speech_request(req, set(VOICE_MAP.keys()))

    # Resolve speaker WAV. Unknown voice is a client error — do NOT
    # silently fall through to the default voice like v2.1.0 did.
    adhoc = bool(custom_wav_path)
    if adhoc:
        speaker_wav = custom_wav_path
        voice_id = "adhoc"  # cache key collapses to "adhoc" (actual bypass is enforced below)
    else:
        requested = req.voice.lower()
        if requested not in VOICE_MAP:
            if custom_wav_path and os.path.exists(custom_wav_path):
                os.unlink(custom_wav_path)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown voice '{req.voice}'. Available: {sorted(VOICE_MAP.keys())}. "
                    f"Pass an uploaded 'custom_voice_file' for adhoc cloning, or add the "
                    f"voice to voices.json."
                ),
            )
        v_file = VOICE_MAP[requested]
        speaker_wav = os.path.join(VOICE_ASSET_DIR, v_file)
        voice_id = requested
        if not os.path.exists(speaker_wav):
            # Configured in voices.json but the wav file is missing on disk
            # — that's a server-config issue, not a client error.
            raise HTTPException(
                status_code=500,
                detail=f"Voice '{requested}' is mapped but the wav file is missing on disk.",
            )

    params = {
        "temperature":        req.temperature,
        "length_penalty":     req.length_penalty,
        "repetition_penalty": req.repetition_penalty,
        "top_k":              req.top_k,
        "top_p":              req.top_p,
    }
    # VoxCPM-specific params — only include when explicitly set by client
    if req.cfg_value is not None:
        params["cfg_value"] = req.cfg_value
    if req.inference_timesteps is not None:
        params["inference_timesteps"] = req.inference_timesteps
    cache_key = hashlib.md5(
        f"{req.input}{voice_id}{req.speed}{req.response_format}"
        f"{req.temperature}{req.length_penalty}{req.repetition_penalty}{req.top_k}{req.top_p}"
        f"{req.cfg_value}{req.inference_timesteps}".encode()
    ).hexdigest()
    final_output_path = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.{req.response_format}")

    # Adhoc voice cloning ALWAYS bypasses the MD5 cache: the uploaded
    # voice has no stable identity (temp-file path changes per request),
    # and caching it would just pollute the cache with single-use junk
    # entries. Matches uttera-tts-vllm v1.2.0 semantics.
    bypass_cache = header_bypass or (req.cache is False) or adhoc
    cache_effectively_on = CACHE_TTL_MINUTES > 0 and not bypass_cache
    cache_lock = _cache_locks.setdefault(cache_key, asyncio.Lock())
    async with cache_lock:
        if cache_effectively_on and os.path.exists(final_output_path):
            age_min = (time.time() - os.path.getmtime(final_output_path)) / 60
            if age_min < CACHE_TTL_MINUTES:
                resp = FileResponse(final_output_path, media_type=f"audio/{req.response_format}")
                resp.headers["X-Cache"] = "HIT"
                # Cache hit — count once per request but don't re-bill
                # characters (the caller already paid when the entry was
                # first populated).
                _SYNTHESIS_TOTAL.labels(
                    response_format=req.response_format, route="CACHE", cache="HIT"
                ).inc()
                _REQUESTS_BY_ROUTE_TOTAL.labels(route="CACHE").inc()
                return resp
            os.remove(final_output_path)

        word_count = _count_words(req.input)
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        item = _WorkItem(
            text=req.input,
            speaker_wav=speaker_wav,
            language=req.language,
            speed=req.speed,
            params=params,
            word_count=word_count,
            future=future,
        )

        global _work_queue_words
        _work_queue_words += word_count
        await _work_queue.put(item)

        _INFLIGHT_GAUGE.inc()
        _synth_t0 = time.monotonic()
        try:
            audio_bytes, route = await future
        except Exception as e:
            # Distinguish client-input errors (bogus audio body in
            # custom_voice_file, unsupported codec) from true server
            # faults. The backend signals decode failures via
            # messages containing "AudioDecoder", "Could not open",
            # "Invalid data", or "Format not recognised" — surface
            # those as HTTP 400 with a trimmed message instead of 500.
            msg = str(e)
            low = msg.lower()
            is_decode_error = adhoc and any(
                m in low for m in (
                    "audiodecoder",
                    "could not open",
                    "invalid data found",
                    "format not recognised",
                    "format not recognized",
                )
            )
            if is_decode_error:
                # Trim the full traceback to just the relevant line.
                short = msg.strip().splitlines()[-1][:200] or "decode failed"
                _ERRORS_TOTAL.labels(type="decode").inc()
                _INFLIGHT_GAUGE.dec()
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Failed to decode custom_voice_file — not a valid "
                        f"audio stream or unsupported codec ({short})."
                    ),
                )
            _ERRORS_TOTAL.labels(type="model").inc()
            _INFLIGHT_GAUGE.dec()
            raise HTTPException(status_code=500, detail=msg)
        finally:
            if custom_wav_path and os.path.exists(custom_wav_path):
                os.unlink(custom_wav_path)

        # Record the synthesis-phase duration (queue-put through
        # future-resolved). Lane-tagged so dashboards can separate
        # hot-lane vs cold-pool latency.
        _op_synth = "synthesis_cold" if route in ("COLD-POOL",) else "synthesis_hot"
        _INFERENCE_DURATION.labels(op=_op_synth).observe(time.monotonic() - _synth_t0)

        temp_wav = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4()}.wav")
        output_path = final_output_path if cache_effectively_on else os.path.join(
            tempfile.gettempdir(), f"tts_{uuid.uuid4()}.{req.response_format}")
        try:
            with open(temp_wav, "wb") as f:
                f.write(audio_bytes)
            with _INFERENCE_DURATION.labels(op="ffmpeg_encode").time():
                convert_audio(temp_wav, output_path, req.response_format)
        except Exception as e:
            _ERRORS_TOTAL.labels(type="encoding").inc()
            _INFLIGHT_GAUGE.dec()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if os.path.exists(temp_wav):
                os.unlink(temp_wav)

    if not cache_effectively_on:
        background_tasks.add_task(lambda p=output_path: os.path.exists(p) and os.unlink(p))
    response = FileResponse(output_path, media_type=f"audio/{req.response_format}")
    response.headers["X-Route"] = route
    # Symmetric with uttera-tts-vllm: when the client uploads a voice for
    # cloning, label the X-Cache as ADHOC (the cache was skipped because
    # of the cloning, not because of a client opt-out).
    if adhoc:
        x_cache = "ADHOC"
    elif header_bypass or (req.cache is False):
        x_cache = "BYPASS"
    elif CACHE_TTL_MINUTES > 0:
        x_cache = "MISS"
    else:
        x_cache = "DISABLED"
    response.headers["X-Cache"] = x_cache

    # Metrics: count the synthesis + lane, and bill characters. The
    # route label matches the X-Route header exactly; adhoc requests
    # override route=ADHOC on the metric so dashboards reflect what
    # the client sees even though item.route may internally be HOT.
    metric_route = "ADHOC" if adhoc else route
    _SYNTHESIS_TOTAL.labels(
        response_format=req.response_format, route=metric_route, cache=x_cache
    ).inc()
    _REQUESTS_BY_ROUTE_TOTAL.labels(route=metric_route).inc()
    _CHARACTERS_SYNTHESISED_TOTAL.labels(response_format=req.response_format).inc(len(req.input))
    _INFLIGHT_GAUGE.dec()
    return response

# -------------------------------
# 14. Endpoint: POST /v1/audio/speech/stream  (hot lane only)
# -------------------------------
# Streaming delegates to `_backend.infer_stream()` which yields the WAV
# header as its first element, followed by raw PCM chunks. Backends that
# do not support streaming raise NotImplementedError — the endpoint
# wraps this into HTTP 501.


async def stream_tts_hot_lane_async(text: str, lang: str, speaker_wav: str,
                                     speed: float, params: dict):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def sync_produce():
        try:
            for chunk in _backend.infer_stream(
                text=text,
                voice_wav_path=speaker_wav,
                language=lang,
                speed=speed,
                params=params,
            ):
                asyncio.run_coroutine_threadsafe(queue.put(chunk), loop).result()
        except Exception as e:
            asyncio.run_coroutine_threadsafe(queue.put(e), loop).result()
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    producer_thread = threading.Thread(target=sync_produce, daemon=True)
    producer_thread.start()
    while True:
        item = await queue.get()
        if item is None:
            break
        if isinstance(item, Exception):
            raise item
        yield item


@app.post("/v1/audio/speech/stream")
async def create_speech_stream(request: Request):
    """
    Streaming TTS endpoint (Hot Lane only). Returns audio/wav chunked.
    HTTP 503 if hot worker not loaded or busy.
    """
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        data = await request.json()
        try:
            req = SpeechRequest(**data)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())
    else:
        form_data = await request.form()
        try:
            req = SpeechRequest(
                input=form_data.get("input"),
                voice=form_data.get("voice", DEFAULT_VOICE),
                response_format="wav",
                speed=float(form_data.get("speed", 1.0)),
                language=form_data.get("language", os.environ.get("DEFAULT_LANGUAGE", "en")),
                temperature=float(form_data.get("temperature", os.environ.get("DEFAULT_TEMPERATURE", 0.75))),
                length_penalty=float(form_data.get("length_penalty", os.environ.get("DEFAULT_LENGTH_PENALTY", 1.0))),
                repetition_penalty=float(form_data.get("repetition_penalty", os.environ.get("DEFAULT_REPETITION_PENALTY", 5.0))),
                top_k=int(form_data.get("top_k", os.environ.get("DEFAULT_TOP_K", 50))),
                top_p=float(form_data.get("top_p", os.environ.get("DEFAULT_TOP_P", 0.85))),
            )
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

    if not req.input or not req.input.strip():
        raise HTTPException(status_code=422, detail="'input' must be a non-empty string.")
    _validate_speech_request(req, set(VOICE_MAP.keys()))

    if not _hot_worker_ready():
        raise HTTPException(status_code=503, detail="Hot worker not loaded. Streaming unavailable.")
    if not model_lock.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Hot worker busy. Use /v1/audio/speech for queued synthesis.")

    requested = req.voice.lower()
    if requested not in VOICE_MAP:
        model_lock.release()  # release the lock we just acquired before raising
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice '{req.voice}'. Available: {sorted(VOICE_MAP.keys())}.",
        )
    v_file = VOICE_MAP[requested]
    speaker_wav = os.path.join(VOICE_ASSET_DIR, v_file)
    if not os.path.exists(speaker_wav):
        model_lock.release()
        raise HTTPException(
            status_code=500,
            detail=f"Voice '{requested}' is mapped but the wav file is missing on disk.",
        )

    params = {
        "temperature": req.temperature, "length_penalty": req.length_penalty,
        "repetition_penalty": req.repetition_penalty, "top_k": req.top_k, "top_p": req.top_p,
    }
    if req.cfg_value is not None:
        params["cfg_value"] = req.cfg_value
    if req.inference_timesteps is not None:
        params["inference_timesteps"] = req.inference_timesteps

    # Metrics: streaming is hot-lane-only, cache-disabled by construction.
    _SYNTHESIS_TOTAL.labels(
        response_format="wav", route="HOT", cache="DISABLED"
    ).inc()
    _REQUESTS_BY_ROUTE_TOTAL.labels(route="HOT").inc()
    _CHARACTERS_SYNTHESISED_TOTAL.labels(response_format="wav").inc(len(req.input))
    _INFLIGHT_GAUGE.inc()
    _stream_t0 = time.monotonic()

    async def generate_and_release():
        try:
            async for chunk in stream_tts_hot_lane_async(req.input, req.language, speaker_wav, req.speed, params):
                yield chunk
            _INFERENCE_DURATION.labels(op="synthesis_hot").observe(time.monotonic() - _stream_t0)
        except Exception:
            _ERRORS_TOTAL.labels(type="model").inc()
            raise
        finally:
            _INFLIGHT_GAUGE.dec()
            model_lock.release()

    return StreamingResponse(generate_and_release(), media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_tts:app", host="0.0.0.0", port=9004)
