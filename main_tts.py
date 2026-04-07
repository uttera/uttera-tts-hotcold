#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Coqui TTS Server (Hybrid Model)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <https://www.gnu.org/licenses/>.
#
# main_tts.py - Coqui TTS Hybrid-Worker Server
# Copyright (C) 2025 Gemini (Author) & Hugo L. Espuny (Supervisor)
#
# Package: coqui-tts-server
# Version: 1.5.7
# Maintainer: Uttera, Hugo L. Espuny
# Description: High-performance TTS server with personality tuning and GIL-bypass concurrency.
#
# CHANGELOG:
# - 1.5.7 (2026-04-07): Added cold lane WAV-missing diagnostic: when the cold subprocess exits 0
#   but produces no output WAV (empty text, silent crash, driver issue), full stdout/stderr are
#   logged and a descriptive RuntimeError is raised instead of the opaque downstream error.
#   Added cold_workers_in_flight to GET /health under smart_routing (mirrors whisper v1.4.7).
#   Validated with 40-clip Spanish stress test vs v1.4.10 (production, caché limpia):
#   v1.5.7 40/40 OK vs v1.4.10 13/40 OK (27 HTTP 500 por OOM en cold lane sin fallback).
#   Error rate 67.5% → 0% under concurrent load. Cold EMA ~30s, MIN_COLD_VRAM_GB=5.0.
# - 1.5.6 (2026-04-06): VRAM pre-check before cold lane dispatch. Branch C now queries
#   torch.cuda.mem_get_info() before spawning a cold subprocess. If effective free VRAM
#   (raw free minus in_flight × MIN_COLD_VRAM_GB) is below MIN_COLD_VRAM_GB (default 5.0 GB
#   for XTTS-v2, configurable via .env), the request is rerouted to the hot lane queue
#   immediately instead of wasting ~10s on a model load that will OOM mid-way. Free VRAM,
#   MIN_COLD_VRAM_GB, and vram_sufficient_for_cold exposed in GET /health under smart_routing.
#   Same feature applied to whisper-stt-local-server v1.4.7 (default 4.0 GB).
# - 1.5.5 (2026-04-06): Fixed model_lock deadlock under client timeout (burst load). Branch B and
#   the Branch C fallback previously used two separate asyncio.to_thread calls: one to acquire
#   model_lock and one to run synthesis. If asyncio cancelled the coroutine (client timeout)
#   between the two awaits, model_lock was left permanently acquired, deadlocking the server.
#   Fixed by introducing _run_tts_hot_locked() which performs acquire + synthesize + release
#   inside a single asyncio.to_thread call. Confirmed by burst-of-40 test: previous version
#   deadlocked after client timeouts; this version processes all requests in queue even after
#   client disconnect.
# - 1.5.4 (2026-04-06): Auto-calibration of COLD_START_TIME_SECONDS. An EMA (alpha=0.2) of
#   measured cold lane completion times now replaces the static COLD_START_TIME_SECONDS as the
#   router threshold once at least one cold lane has completed successfully. COLD_START_TIME_SECONDS
#   in .env becomes an initial hint / fallback used until the EMA is seeded. _get_cold_start_time()
#   returns the live EMA or the configured fallback. cold_start_calibrated and
#   cold_ema_start_seconds exposed in GET /health under smart_routing.
# - 1.5.3 (2026-04-06): EMA no longer updated from fallback path. The fallback elapsed
#   includes cold-lane failure time (~COLD_START_TIME_SECONDS), inflating spw and causing
#   the router to dispatch cold lanes more aggressively on subsequent bursts (positive
#   feedback loop → more OOMs → more fallbacks). EMA is now updated only from clean
#   Branch A and B completions. Also applied to whisper-stt-local-server (both transcription
#   and translation fallback paths).
# - 1.5.2 (2026-04-06): Cold-Lane Fallback to Hot Lane. When a cold lane subprocess exits
#   with a non-zero code (CUDA OOM under burst load), the request is transparently retried
#   on the hot lane queue instead of returning HTTP 500. Same Branch-B mechanism: adds
#   word_count to _hot_queue_words before waiting. Warmup text changed to 8 words for a
#   more representative initial EMA seed (prevents over-eager cold-lane dispatch at startup).
# - 1.5.1 (2026-04-06): Startup EMA Warmup. After the hot worker loads, a short synthesis
#   ("System online.") is run through the hot lane via the FastAPI lifespan event to seed
#   _hot_ema_spw before the first real request arrives. Without this, EMA=None at startup
#   caused every concurrent request to go to cold lane (Branch C), triggering CUDA OOM when
#   multiple workers loaded the model simultaneously. The warmup runs after Application startup
#   and prints the measured spw so the operator can verify throughput at startup. Failure is
#   logged but non-fatal: the server starts in uncalibrated mode rather than refusing to start.
# - 1.5.0 (2026-04-06): Smart Hot-Lane Routing. Three-branch router replaces the previous
#   binary hot/cold decision. Branch A: hot lane free → use immediately (unchanged). Branch B:
#   hot lane busy but estimated drain time < COLD_START_TIME_SECONDS * HOT_QUEUE_SAFETY_FACTOR
#   → queue for hot lane (asyncio.to_thread on model_lock.acquire, non-blocking). Branch C:
#   hot lane busy and drain estimate exceeds threshold → spawn cold lane as before. The drain
#   estimate uses a per-request EMA (alpha=0.2) of seconds-per-word, updated after each
#   successful hot-lane synthesis. _hot_queue_words tracks all words in the hot pipeline
#   (being synthesised + waiting) so late-arriving requests see the full queue depth.
#   Falls back to Branch C when the EMA is not yet calibrated (first concurrency cycle).
#   New env vars: COLD_START_TIME_SECONDS (default 10.0s), HOT_QUEUE_SAFETY_FACTOR (default 0.8).
#   Routing stats and live EMA exposed in GET /health under 'smart_routing'.
#   Verified on RTX 50-series: 3 concurrent requests resolved in 4.4s total (all hot-queued,
#   drain estimates well below threshold). 6 concurrent requests: first 3 hot-queued, last 3
#   correctly dispatched to cold lanes when drain_est reached 10.5s > 8.0s threshold.
# - 1.4.10 (2026-04-03): Added GET /v1/models endpoint (OpenAI spec compliance). Returns tts-1 and tts-1-hd. Version string moved to SERVER_VERSION constant.
# - 1.4.9 (2026-04-03): Pinned torch==2.9.0, torchaudio==2.9.0, torchcodec==0.8.1, transformers>=4.35.2,<5.0.0 to match production (sphinx). setup.sh now selects python3.12 first (Python 3.13+ has no wheels for these packages).
# - 1.4.8 (2026-04-03): Reverted torchcodec stub monkey-patch (unnecessary on production). Restored torchcodec in requirements.txt. Kept transformers<5.0.0 pin.
# - 1.4.7 (2026-04-03): Fixed torchcodec/CUDA NPP startup crash. Stub catches RuntimeError, injected before transformers import. transformers pinned <5.0.0.
# - 1.4.6 (2026-04-02): Removed hardcoded sentencepiece==0.2.0 from setup.sh (no wheel for Python 3.14).
# - 1.4.5 (2026-04-02): Moved transformers/isin_mps_friendly patch from setup.sh to a Python monkey-patch in main_tts.py. Survives venv upgrades.
# - 1.4.4 (2026-04-02): ffmpeg errors no longer leak internal paths in HTTP 500 responses.
# - 1.4.3 (2026-04-02): Exposed hot worker load error in GET /health via hot_worker_error field.
# - 1.4.2 (2026-04-02): Fixed Cold Lane indefinite hang via asyncio.wait_for timeout (COLD_LANE_TIMEOUT_SECONDS). Fixed cache race condition via per-key asyncio.Lock.
# - 1.4.1 (2026-04-02): SECURITY: Fixed code injection in Cold Lane. Text is now passed via env var TTS_INPUT_TEXT instead of f-string interpolation.
# - 1.4.0 (2026-04-02): Added POST /v1/audio/speech/stream endpoint (Hot Lane only, WAV chunked).
# - 1.3.0 (2026-04-02): Added GET /health endpoint. Added cache TTL expiration via CACHE_TTL_MINUTES env var.
# - 1.2.0 (2026-03-03): Added personality parameters, discovery endpoint, and API parity for Cold Lane.
# - 1.1.4 (2026-02-28): Golden version release. Performance verified for Uttera nodes.
# - 1.1.0 (2026-02-28): Restoration from Sphinx v123. Implemented Hot/Cold concurrency and GIL bypass.
# - 1.0.3 (2026-02-28): No-Sudo workflow, local assets structure, and CLI prerequisites.
# - 1.0.0 (2025-11-20): Initial production release.
#
# --- Architecture Summary ---
#
# This server implements a hybrid "hot/cold" worker model to provide
# true concurrent TTS synthesis from a single FastAPI instance.
#
# * MAIN LANE (Hot Worker):
#   An XTTSv2 model is pre-loaded into VRAM on startup ('tts_hot_worker')
#   and pre-heated. Protected by 'model_lock' (threading.Lock).
#
# * CHILD LANE (Cold Worker / GIL Bypass):
#   If the main lane is busy, the request is rerouted to an independent
#   Python subprocess ('asyncio.create_subprocess_exec').
#   This bypasses the Python Global Interpreter Lock (GIL), allowing
#   multiple GPU-intensive syntheses to run in parallel.
#
# * API PARITY:
#   The Child Lane executes a Python one-liner that uses the TTS.api directly.
#   This ensures all personality parameters (temperature, penalties, etc.)
#   behave exactly the same across all lanes, which the 'tts' CLI does not support.
#
# * STREAM LANE (Hot Worker / inference_stream):
#   POST /v1/audio/speech/stream uses XTTS-v2's inference_stream() to yield
#   PCM audio chunks in real time via a WAV-framed StreamingResponse.
#   Runs exclusively on the Hot Lane (model_lock). Returns HTTP 503 if busy.
#   No caching — audio is generated and sent in real time.
#   A sync producer thread feeds chunks into an asyncio.Queue to bridge
#   the blocking model iterator with the async response generator.
#
# * Deadlock Fixes:
#   1. (License): The 'COQUI_TOS_AGREED=1' env var is passed to the
#      subprocess to prevent it from hanging on the [y/n] license prompt.
#   2. (Logs): In DEBUG mode, subprocess output is directed to stdout 
#      directly to ensure visibility without buffer deadlocks.
#

import os
import time
import uuid
import shutil
import struct
import asyncio
import hashlib
import tempfile
import subprocess
import threading
import warnings
import sys
from contextlib import asynccontextmanager
from typing import Optional, List, Union
from dotenv import load_dotenv

# Load environment variables from .env if present
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_paths = [
    os.path.join(BASE_DIR, ".env"),
    os.path.join(os.path.dirname(BASE_DIR), ".env")
]
for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

# Suppress noisy warnings
warnings.filterwarnings('ignore', message=".*pkg_resources is deprecated.*")
warnings.filterwarnings('ignore', message=".*_register_pytree_node` is deprecated.*")

# Monkey-patch: inject isin_mps_friendly if missing from transformers.
# Coqui XTTS-v2 (0.27.5) calls this function which is absent in some transformers versions.
# This replaces the fragile append-to-venv-file patch previously applied by setup.sh,
# making the fix version-upgrade-safe and repository-resident.
# Must run before 'from TTS.api import TTS' triggers the transformers import chain.
try:
    from transformers.pytorch_utils import isin_mps_friendly  # noqa: F401 — just checking presence
except ImportError:
    import torch as _torch
    import transformers.pytorch_utils as _tpu
    def _isin_mps_friendly(elements, test_elements):
        return _torch.isin(elements, test_elements)
    _tpu.isin_mps_friendly = _isin_mps_friendly

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request, BackgroundTasks
from pydantic import BaseModel
from fastapi.responses import FileResponse, StreamingResponse
from TTS.api import TTS
import torch

# -------------------------------
# 1. Configuration & Paths
# -------------------------------
PARENT_DIR = os.path.dirname(BASE_DIR)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

# Helper to find venv paths (local first, then parent)
def find_venv_path(rel_path):
    local = os.path.join(BASE_DIR, rel_path)
    parent = os.path.join(PARENT_DIR, rel_path)
    if os.path.exists(local): return local
    if os.path.exists(parent): return parent
    return local # Fallback to local if not found anywhere

VENV_PYTHON = os.environ.get("VENV_PYTHON", find_venv_path("venv/bin/python"))
MODEL_NAME = os.environ.get("TTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")

# Storage Paths
AUDIO_CACHE_DIR = os.path.join(ASSETS_DIR, "cache")
MODEL_CACHE_DIR = os.path.join(ASSETS_DIR, "models")
VOICE_ASSET_DIR = os.path.join(ASSETS_DIR, "voices")

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
os.makedirs(VOICE_ASSET_DIR, exist_ok=True)

# Override from Environment if provided
AUDIO_CACHE_DIR = os.environ.get("AUDIO_CACHE_DIR", AUDIO_CACHE_DIR)
MODEL_CACHE_DIR = os.environ.get("TTS_HOME", MODEL_CACHE_DIR)
VOICE_ASSET_DIR = os.environ.get("VOICE_ASSET_DIR", VOICE_ASSET_DIR)

DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Cache TTL: files older than this (in minutes) are treated as expired.
# Default: 10080 minutes = 7 days. Set to 0 to disable expiration.
CACHE_TTL_MINUTES = int(os.environ.get("CACHE_TTL_MINUTES", 10080))

# Cold Lane timeout: max seconds to wait for a cold worker subprocess before killing it.
# Default: 120s. Prevents hung subprocesses (OOM, driver crash) from blocking requests forever.
COLD_LANE_TIMEOUT_SECONDS = int(os.environ.get("COLD_LANE_TIMEOUT_SECONDS", 120))

# --- Smart Hot-Lane Routing ---
# Initial hint for cold lane startup time. Used as the routing threshold until the auto-calibrated
# EMA (_cold_ema_start) is seeded by the first successful cold lane completion. After that,
# _get_cold_start_time() returns the live EMA instead. Set in .env only if cold lanes never run
# during startup and you want a specific initial bias.
# Default: 10s (typical RTX 50-series / mid-range GPU cold start).
COLD_START_TIME_SECONDS = float(os.environ.get("COLD_START_TIME_SECONDS", 10.0))

# Safety margin applied to COLD_START_TIME_SECONDS when comparing with hot queue drain estimate.
# 0.8 means "queue hot only if we expect to finish at least 20% before the cold lane would be ready".
# Lower values = more conservative (bias toward cold lane). Range: 0.0–1.0.
HOT_QUEUE_SAFETY_FACTOR = float(os.environ.get("HOT_QUEUE_SAFETY_FACTOR", 0.8))

# Minimum free VRAM (GB) required to spawn a cold lane worker.
# If free VRAM is below this threshold at dispatch time, Branch C redirects to the hot lane
# queue instead of spawning a subprocess that will OOM mid-load (~10s wasted before failure).
# Default: 5.0 GB (XTTS-v2 ~3.5 GB model + loading overhead).
# Set to 0 to disable the VRAM check (not recommended on memory-constrained hardware).
MIN_COLD_VRAM_GB = float(os.environ.get("MIN_COLD_VRAM_GB", 5.0))

# EMA smoothing factor for the hot-lane seconds-per-word estimator.
# Lower = slower to adapt (more stable). Higher = reacts faster to recent requests.
_HOT_EMA_ALPHA = 0.2

# --- Voice Mapping: OpenAI Standards & Elite Gallery ---
VOICE_MAP = {
    "alloy": "standard/alloy.wav",
    "echo": "standard/echo.wav",
    "fable": "standard/fable.wav",
    "onyx": "standard/onyx.wav",
    "nova": "standard/nova.wav",
    "shimmer": "standard/shimmer.wav",
    
    "narrator": "elite/narrator.wav",
    "voice-b": "elite/redacted-voice.wav",
    "voice-c": "elite/redacted-voice.wav",
    "voice-a": "elite/redacted-voice.wav",
    "voice-d": "elite/redacted.wav",
    "voice-e": "elite/redacted.wav",
    "voice-f": "elite/redacted.wav",
    "voice-g": "elite/redacted.wav",
    "voice-h": "elite/redacted.wav"
}

SERVER_VERSION = "1.5.7"

# -------------------------------
# 2. Concurrency & Model Loading
# -------------------------------
model_lock = threading.Lock()
tts_hot_worker = None
# Stores the error message if the hot worker fails to load. Exposed via /health.
hot_worker_error = None

# Per-cache-key asyncio locks. Prevents two concurrent requests with the same cache key
# from both synthesizing the same audio. The second request waits for the lock, then
# finds the file already written and returns it from cache without re-synthesizing.
# Safe without a threading.Lock because asyncio runs in a single event loop thread;
# dict.setdefault() is atomic within it.
_cache_locks: dict = {}

def load_hot_worker():
    global tts_hot_worker, hot_worker_error
    if DEBUG: print(f"[*] Loading HOT WORKER model: {MODEL_NAME}", flush=True)
    try:
        torch.backends.cudnn.benchmark = True
        worker = TTS(model_name=MODEL_NAME, progress_bar=False)
        worker.to("cuda")

        warmup_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP["alloy"])
        if os.path.exists(warmup_wav):
            worker.tts("System online.", speaker_wav=warmup_wav, language="en")
            if DEBUG: print("[+] Hot worker warmed up and ready on GPU.", flush=True)
        tts_hot_worker = worker
    except Exception as e:
        # Store the error so /health can expose degraded state to operators and proxies.
        hot_worker_error = str(e)
        print(f"[!] CRITICAL ERROR: Failed to load hot worker: {e}", flush=True)

load_hot_worker()

# -------------------------------
# 2b. Smart Routing Telemetry
# -------------------------------
# All fields below are accessed exclusively from the asyncio event loop thread.
# No threading.Lock required — asyncio.to_thread returns control to the loop before
# we read or write these, so there are no concurrent mutations.

# Exponential moving average of hot-lane synthesis time in seconds per word.
# None = not yet calibrated (no successful hot-lane synthesis has completed yet).
_hot_ema_spw: Optional[float] = None

# Total words currently tracked in the hot-lane pipeline: the request being synthesised
# plus any requests waiting to acquire model_lock. Updated before enqueue, decremented
# after completion so that arriving requests always see the full queue depth.
_hot_queue_words: int = 0

# EMA of successful cold lane completion times (seconds). None = not yet calibrated.
# Auto-calibrates COLD_START_TIME_SECONDS so operators don't need to measure it per-hardware.
# Updated after each successful Branch C completion; replaces COLD_START_TIME_SECONDS as the
# router threshold once seeded.
_cold_ema_start: Optional[float] = None
_COLD_EMA_ALPHA = 0.2

# Count of cold lane subprocesses currently in flight (loading model + synthesizing).
# Each in-flight worker reserves MIN_COLD_VRAM_GB from the effective free pool so that
# simultaneous Branch C routing decisions don't over-commit VRAM before any worker allocates.
_cold_workers_in_flight: int = 0


def _update_cold_ema(elapsed: float) -> None:
    """Update the cold-lane time EMA after a successful cold lane synthesis."""
    global _cold_ema_start
    if _cold_ema_start is None:
        _cold_ema_start = elapsed
    else:
        _cold_ema_start = _COLD_EMA_ALPHA * elapsed + (1.0 - _COLD_EMA_ALPHA) * _cold_ema_start


def _get_cold_start_time() -> float:
    """Return the auto-calibrated cold start time EMA, or COLD_START_TIME_SECONDS as fallback."""
    return _cold_ema_start if _cold_ema_start is not None else COLD_START_TIME_SECONDS


def _free_vram_gb() -> Optional[float]:
    """Return current free VRAM in GB, or None if CUDA is unavailable."""
    if not torch.cuda.is_available():
        return None
    free_bytes, _ = torch.cuda.mem_get_info()
    return free_bytes / (1024 ** 3)


def _has_vram_for_cold_lane() -> bool:
    """
    Return True if there is enough free VRAM to load one more cold XTTS-v2 worker.

    Accounts for in-flight cold workers by reserving MIN_COLD_VRAM_GB per worker from
    the effective free pool, preventing burst routing decisions from over-committing
    memory before any cold subprocess has started allocating.

    effective_free = gpu_free - (_cold_workers_in_flight × MIN_COLD_VRAM_GB)
    dispatch cold  if  effective_free >= MIN_COLD_VRAM_GB
    """
    if MIN_COLD_VRAM_GB <= 0:
        return True  # check disabled via env var
    free = _free_vram_gb()
    if free is None:
        return True  # CPU mode: no VRAM constraint
    effective_free = free - (_cold_workers_in_flight * MIN_COLD_VRAM_GB)
    return effective_free >= MIN_COLD_VRAM_GB


def _count_words(text: str) -> int:
    """Word count proxy for synthesis time estimation. Minimum 1 to avoid division by zero."""
    return max(1, len(text.split()))


def _update_hot_ema(elapsed: float, word_count: int) -> None:
    """Update the seconds-per-word EMA after a successful hot-lane synthesis."""
    global _hot_ema_spw
    spw = elapsed / word_count
    if _hot_ema_spw is None:
        _hot_ema_spw = spw
    else:
        _hot_ema_spw = _HOT_EMA_ALPHA * spw + (1.0 - _HOT_EMA_ALPHA) * _hot_ema_spw


def _should_queue_hot(incoming_word_count: int) -> bool:
    """
    Return True if it is cheaper to wait for the hot lane than to start a cold lane.

    Decision formula:
        estimated_drain_time = _hot_queue_words * _hot_ema_spw
        queue_hot  if  estimated_drain_time < COLD_START_TIME_SECONDS * HOT_QUEUE_SAFETY_FACTOR

    incoming_word_count is NOT included in the estimate: we are asking "how long until the
    hot lane is free for me?", not "how long will my request take once it starts".

    Returns False (→ cold lane) when the EMA is not yet calibrated (first cycle).
    """
    if _hot_ema_spw is None:
        return False
    estimated_drain = _hot_queue_words * _hot_ema_spw
    threshold = _get_cold_start_time() * HOT_QUEUE_SAFETY_FACTOR
    return estimated_drain < threshold


async def _warmup_ema():
    """
    Run a short synthesis through the hot lane at startup to seed _hot_ema_spw.
    Seeds the EMA before the first real request arrives, preventing the EMA=None →
    cold-lane cascade that causes CUDA OOM under burst load at startup.
    Failure is non-fatal: the server starts in uncalibrated mode with a log warning.
    """
    if tts_hot_worker is None:
        return  # degraded mode — nothing to warm up

    warmup_text = "All systems nominal. Standing by for further orders."
    word_count = _count_words(warmup_text)
    speaker_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP.get("alloy", "elite/alloy.wav"))
    if not os.path.exists(speaker_wav):
        print("WARMUP: Speaker WAV not found. Skipping EMA seed.", flush=True)
        return

    print("WARMUP: Seeding EMA with synthesis...", flush=True)
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        try:
            params = {"temperature": 0.75, "length_penalty": 1.0, "repetition_penalty": 5.0, "top_k": 50, "top_p": 0.85}
            t0 = time.monotonic()
            await asyncio.to_thread(run_tts_hot_lane, warmup_text, "en", speaker_wav, 1.0, tmp_path, params)
            elapsed = time.monotonic() - t0
            _update_hot_ema(elapsed, word_count)
            print(f"WARMUP: EMA seeded. spw={_hot_ema_spw:.4f} (elapsed={elapsed:.2f}s for {word_count} words)", flush=True)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        print(f"WARMUP: Failed to seed EMA ({e}). Server starting in uncalibrated mode.", flush=True)


# -------------------------------
# 3. OpenAI Schema Models
# -------------------------------
class SpeechRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str = "alloy"
    response_format: str = "mp3"
    speed: float = 1.0
    language: str = os.environ.get("DEFAULT_LANGUAGE", "en")
    temperature: float = float(os.environ.get("DEFAULT_TEMPERATURE", 0.75))
    length_penalty: float = float(os.environ.get("DEFAULT_LENGTH_PENALTY", 1.0))
    repetition_penalty: float = float(os.environ.get("DEFAULT_REPETITION_PENALTY", 5.0))
    top_k: int = int(os.environ.get("DEFAULT_TOP_K", 50))
    top_p: float = float(os.environ.get("DEFAULT_TOP_P", 0.85))

@asynccontextmanager
async def _lifespan(application: FastAPI):
    await _warmup_ema()
    yield


app = FastAPI(title="Coqui TTS Server", version=SERVER_VERSION, lifespan=_lifespan)

# -------------------------------
# 4. Core Logic: The Two Lanes
# -------------------------------

def convert_audio(input_path: str, output_path: str, fmt: str):
    if fmt == "wav":
        shutil.copy(input_path, output_path)
        return
    
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if fmt == "mp3": cmd.extend(["-codec:a", "libmp3lame", "-qscale:a", "2"])
    elif fmt == "opus": cmd.extend(["-codec:a", "libopus", "-b:a", "64k"])
    elif fmt == "flac": cmd.extend(["-codec:a", "flac"])
    cmd.append(output_path)
    
    try:
        subprocess.run(cmd, capture_output=(not DEBUG), check=True)
    except subprocess.CalledProcessError as e:
        # Log full detail internally; expose only a generic message to the client
        # to avoid leaking internal paths and system info in HTTP 500 responses.
        print(f"[!] ffmpeg error (code {e.returncode}): {e}", flush=True)
        raise RuntimeError(f"Audio conversion to {fmt} failed (ffmpeg exited {e.returncode})")

def _run_tts_hot_locked(text: str, lang: str, speaker_wav: str, speed: float, output_path: str, params: dict):
    """
    Acquire model_lock, synthesize, release — all inside a single thread.

    Always called via asyncio.to_thread(). Keeping acquire and release in the same thread
    call guarantees the lock is released even if the calling coroutine is cancelled (e.g.
    client timeout). A two-step pattern (await to_thread(lock.acquire) + await to_thread(work)
    + release in coroutine finally) leaves the lock permanently acquired if a CancelledError
    fires between the two awaits, deadlocking the server.
    """
    model_lock.acquire()
    try:
        run_tts_hot_lane(text, lang, speaker_wav, speed, output_path, params)
    finally:
        model_lock.release()


def run_tts_hot_lane(text: str, lang: str, speaker_wav: str, speed: float, output_path: str, params: dict):
    if DEBUG: print(f"--- MAIN LANE: Using hot worker (GPU) ---", flush=True)
    tts_hot_worker.tts_to_file(
        text=text,
        speaker_wav=speaker_wav,
        language=lang,
        file_path=output_path,
        speed=speed,
        temperature=params.get("temperature", 0.75),
        length_penalty=params.get("length_penalty", 1.0),
        repetition_penalty=params.get("repetition_penalty", 5.0),
        top_k=params.get("top_k", 50),
        top_p=params.get("top_p", 0.85)
    )

async def run_tts_child_lane_async(text: str, lang: str, speaker_wav_path: str, speed: float, output_path: str, params: dict):
    if DEBUG: print(f"--- CHILD LANE: Spawning new cold worker... ---", flush=True)
    sub_env = os.environ.copy()
    sub_env["COQUI_TOS_AGREED"] = "1"
    sub_env["TTS_HOME"] = MODEL_CACHE_DIR
    # SECURITY FIX (v1.4.1): Pass text via environment variable instead of interpolating it
    # into the python_code f-string. Interpolation allowed injection of arbitrary Python code
    # if the input text contained triple-quotes or escape sequences.
    sub_env["TTS_INPUT_TEXT"] = text

    # We use a python one-liner to maintain full API parity with the hot worker
    # including personality parameters which the 'tts' CLI does not support.
    # NOTE: 'text' is intentionally NOT interpolated here — read from TTS_INPUT_TEXT env var.
    python_code = f"""
from TTS.api import TTS
import os
os.environ['COQUI_TOS_AGREED'] = '1'
model_name = "{MODEL_NAME}"
tts = TTS(model_name=model_name, progress_bar=False)
tts.to("cuda")
tts.tts_to_file(
    text=os.environ['TTS_INPUT_TEXT'],
    speaker_wav="{speaker_wav_path}",
    language="{lang}",
    file_path="{output_path}",
    speed={speed},
    temperature={params.get("temperature", 0.75)},
    length_penalty={params.get("length_penalty", 1.0)},
    repetition_penalty={params.get("repetition_penalty", 5.0)},
    top_k={params.get("top_k", 50)},
    top_p={params.get("top_p", 0.85)}
)
"""
    cmd = [VENV_PYTHON, "-c", python_code]
    
    if DEBUG: print(f"DEBUG EXEC: Subprocess starting for Cold Lane...", flush=True)
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=sub_env
    )
    # Timeout guard: if the subprocess hangs (OOM, driver crash, etc.) kill it and fail fast.
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=COLD_LANE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        if DEBUG: print(f"[!] Cold worker timed out after {COLD_LANE_TIMEOUT_SECONDS}s. Process killed.", flush=True)
        raise Exception(f"Cold worker timed out after {COLD_LANE_TIMEOUT_SECONDS}s")

    if process.returncode != 0:
        if DEBUG: print(f"[!] Cold worker failed: {stderr.decode()}", flush=True)
        raise Exception(f"Cold worker subprocess failed (code {process.returncode})")

    if not os.path.exists(output_path):
        # exit 0 but no WAV written — subprocess completed without producing output.
        # Log for diagnostics (e.g. silent crash, empty text, driver issue).
        print(
            f"COLD LANE WARNING: exit 0 but WAV not found ({output_path}). "
            f"stdout={stdout.decode()[:300]!r} stderr={stderr.decode()[:300]!r}",
            flush=True
        )
        raise RuntimeError(f"Cold Lane produced no output (exit 0, WAV missing)")

# -------------------------------
# 5. Stream Lane: WAV Header + Async Generator
# -------------------------------

# XTTS-v2 inference_stream output constants (fixed by the model, cannot be changed)
_STREAM_SAMPLE_RATE = 24000
_STREAM_NUM_CHANNELS = 1
_STREAM_BITS_PER_SAMPLE = 16

def make_streaming_wav_header() -> bytes:
    """
    Build a standard WAV header with data_size=0xFFFFFFFF (unknown/streaming length).
    Most audio players and decoders accept this convention for live streams.
    Format: PCM 16-bit, mono, 24000 Hz (XTTS-v2 native output).
    """
    data_size = 0xFFFFFFFF  # unknown length — standard convention for streamed WAV
    riff_size = data_size + 36
    byte_rate = _STREAM_SAMPLE_RATE * _STREAM_NUM_CHANNELS * _STREAM_BITS_PER_SAMPLE // 8
    block_align = _STREAM_NUM_CHANNELS * _STREAM_BITS_PER_SAMPLE // 8
    return struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', riff_size, b'WAVE',
        b'fmt ', 16,
        1,                        # PCM format tag
        _STREAM_NUM_CHANNELS,
        _STREAM_SAMPLE_RATE,
        byte_rate,
        block_align,
        _STREAM_BITS_PER_SAMPLE,
        b'data', data_size
    )

async def stream_tts_hot_lane_async(text: str, lang: str, speaker_wav: str, speed: float, params: dict):
    """
    Async generator for streaming TTS via XTTS-v2 inference_stream (Hot Lane only).

    Yields:
      1. A WAV header (44 bytes) with unknown data size.
      2. PCM int16 audio chunks as they are produced by the model.

    Architecture:
      inference_stream() is a synchronous blocking generator. It runs in a
      dedicated daemon thread (sync_produce) which pushes each chunk into an
      asyncio.Queue. The async generator consumes that queue without blocking
      the event loop. A None sentinel signals end-of-stream. Exceptions from
      the producer are re-raised in the async context.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def sync_produce():
        """Synchronous producer: runs XTTS-v2 inference_stream in a background thread."""
        try:
            if DEBUG: print("--- STREAM LANE: Computing speaker conditioning latents... ---", flush=True)
            gpt_cond_latent, speaker_embedding = (
                tts_hot_worker.synthesizer.tts_model.get_conditioning_latents(
                    audio_path=[speaker_wav]
                )
            )
            if DEBUG: print("--- STREAM LANE: inference_stream started. ---", flush=True)
            for chunk in tts_hot_worker.synthesizer.tts_model.inference_stream(
                text,
                lang,
                gpt_cond_latent,
                speaker_embedding,
                speed=speed,
                temperature=params.get("temperature", 0.75),
                length_penalty=params.get("length_penalty", 1.0),
                repetition_penalty=params.get("repetition_penalty", 5.0),
                top_k=params.get("top_k", 50),
                top_p=params.get("top_p", 0.85),
                stream_chunk_size=20,  # tokens per chunk; lower = lower latency, more requests
            ):
                # Convert float32 tensor in [-1.0, 1.0] to int16 PCM bytes
                pcm_bytes = (chunk.squeeze() * 32767).to(torch.int16).cpu().numpy().tobytes()
                asyncio.run_coroutine_threadsafe(queue.put(pcm_bytes), loop).result()
        except Exception as e:
            asyncio.run_coroutine_threadsafe(queue.put(e), loop).result()
        finally:
            # None sentinel: signals the async consumer that the stream is complete
            asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    # Yield WAV header before starting inference
    yield make_streaming_wav_header()

    producer_thread = threading.Thread(target=sync_produce, daemon=True)
    producer_thread.start()

    # Consume chunks as they arrive from the producer thread
    while True:
        item = await queue.get()
        if item is None:  # sentinel: stream complete
            break
        if isinstance(item, Exception):
            raise item
        yield item

    if DEBUG: print("--- STREAM LANE: Stream complete. ---", flush=True)

# -------------------------------
# 6. Endpoints: /health, /v1/models
# -------------------------------

@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible model listing. Returns the two standard TTS model IDs.
    The 'model' field in synthesis requests is accepted for spec compliance but ignored
    internally — all requests are handled by the configured XTTS-v2 model.
    """
    return {
        "object": "list",
        "data": [
            {"id": "tts-1",    "object": "model", "created": 1677610602, "owned_by": "uttera-legacy"},
            {"id": "tts-1-hd", "object": "model", "created": 1677610602, "owned_by": "uttera-legacy"},
        ]
    }

@app.get("/health")
async def health_check():
    """Returns server liveness, hot worker status, and smart routing telemetry.
    'hot_worker_loaded': false and 'hot_worker_error' set means server is running in degraded mode
    (all requests routed to Cold Lane). The server is still operational but slower.
    'smart_routing.ema_spw': null until the first hot-lane synthesis completes (EMA not calibrated).
    """
    _free = _free_vram_gb()
    routing_stats = {
        "cold_start_time_seconds": round(_get_cold_start_time(), 2),
        "cold_start_calibrated": _cold_ema_start is not None,
        "cold_ema_start_seconds": round(_cold_ema_start, 2) if _cold_ema_start is not None else None,
        "cold_start_configured_seconds": COLD_START_TIME_SECONDS,
        "safety_factor": HOT_QUEUE_SAFETY_FACTOR,
        "threshold_seconds": round(_get_cold_start_time() * HOT_QUEUE_SAFETY_FACTOR, 2),
        "ema_spw": round(_hot_ema_spw, 4) if _hot_ema_spw is not None else None,
        "hot_queue_words": _hot_queue_words,
        "hot_queue_drain_estimate_seconds": round(_hot_queue_words * _hot_ema_spw, 2) if _hot_ema_spw else None,
        "vram_free_gb": round(_free, 2) if _free is not None else None,
        "min_cold_vram_gb": MIN_COLD_VRAM_GB,
        "cold_workers_in_flight": _cold_workers_in_flight,
        "vram_sufficient_for_cold": _has_vram_for_cold_lane(),
    }
    return {
        "status": "ok",
        "version": SERVER_VERSION,
        "model": MODEL_NAME,
        "hot_worker_loaded": tts_hot_worker is not None,
        "hot_worker_error": hot_worker_error,
        "smart_routing": routing_stats,
    }

@app.get("/v1/voices")
async def list_voices():
    """Returns a list of all available voice identifiers."""
    return {"voices": sorted(list(VOICE_MAP.keys()))}

@app.post("/v1/audio/speech")
async def create_speech(request: Request, background_tasks: BackgroundTasks):
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        data = await request.json()
        req = SpeechRequest(**data)
        custom_wav_path = None
    else:
        form_data = await request.form()
        req = SpeechRequest(
            input=form_data.get("input"),
            voice=form_data.get("voice", "alloy"),
            response_format=form_data.get("response_format", "mp3"),
            speed=float(form_data.get("speed", 1.0)),
            language=form_data.get("language", os.environ.get("DEFAULT_LANGUAGE", "en")),
            temperature=float(form_data.get("temperature", os.environ.get("DEFAULT_TEMPERATURE", 0.75))),
            length_penalty=float(form_data.get("length_penalty", os.environ.get("DEFAULT_LENGTH_PENALTY", 1.0))),
            repetition_penalty=float(form_data.get("repetition_penalty", os.environ.get("DEFAULT_REPETITION_PENALTY", 5.0))),
            top_k=int(form_data.get("top_k", os.environ.get("DEFAULT_TOP_K", 50))),
            top_p=float(form_data.get("top_p", os.environ.get("DEFAULT_TOP_P", 0.85)))
        )
        custom_file = form_data.get("custom_voice_file")
        if custom_file and isinstance(custom_file, UploadFile):
            temp_custom = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_custom.write(await custom_file.read())
            temp_custom.close()
            custom_wav_path = temp_custom.name
        else:
            custom_wav_path = None

    if custom_wav_path:
        speaker_wav = custom_wav_path
        voice_id = hashlib.md5(custom_wav_path.encode()).hexdigest()
    else:
        v_file = VOICE_MAP.get(req.voice.lower(), VOICE_MAP["alloy"])
        speaker_wav = os.path.join(VOICE_ASSET_DIR, v_file)
        voice_id = req.voice.lower()
        if not os.path.exists(speaker_wav):
            if DEBUG: print(f"[!] Voice file not found: {speaker_wav}. Falling back to alloy.", flush=True)
            speaker_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP["alloy"])

    lang = req.language
    params = {
        "temperature": req.temperature,
        "length_penalty": req.length_penalty,
        "repetition_penalty": req.repetition_penalty,
        "top_k": req.top_k,
        "top_p": req.top_p
    }
    cache_key = hashlib.md5(f"{req.input}{voice_id}{req.speed}{req.response_format}{req.temperature}{req.length_penalty}{req.repetition_penalty}{req.top_k}{req.top_p}".encode()).hexdigest()
    final_output_path = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.{req.response_format}")

    # Per-key lock: prevents two concurrent requests with the same cache_key from both
    # synthesizing the same audio. The second request waits here, then hits the cache check
    # below and returns the already-written file without launching a new synthesis.
    cache_lock = _cache_locks.setdefault(cache_key, asyncio.Lock())
    async with cache_lock:
        if os.path.exists(final_output_path):
            # Check cache TTL: if CACHE_TTL_MINUTES > 0, expire files older than the threshold
            if CACHE_TTL_MINUTES > 0:
                file_age_minutes = (time.time() - os.path.getmtime(final_output_path)) / 60
                if file_age_minutes >= CACHE_TTL_MINUTES:
                    if DEBUG: print(f"--- ROUTER: Cache expired for {cache_key} (age: {file_age_minutes:.1f}min >= {CACHE_TTL_MINUTES}min). Re-synthesizing. ---", flush=True)
                    os.remove(final_output_path)
                else:
                    if DEBUG: print(f"--- ROUTER: Cache hit for {cache_key} ---", flush=True)
                    return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")
            else:
                if DEBUG: print(f"--- ROUTER: Cache hit for {cache_key} ---", flush=True)
                return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")

        temp_wav = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4()}.wav")
        word_count = _count_words(req.input)
        global _hot_queue_words
        try:
            if tts_hot_worker and model_lock.acquire(blocking=False):
                # ── Branch A: hot lane is free → use it immediately ──────────────
                if DEBUG: print(f"--- ROUTER: Hot lane free. Routing direct. words={word_count} ---", flush=True)
                _hot_queue_words += word_count
                t0 = time.monotonic()
                try:
                    await asyncio.to_thread(run_tts_hot_lane, req.input, lang, speaker_wav, req.speed, temp_wav, params)
                    _update_hot_ema(time.monotonic() - t0, word_count)
                finally:
                    _hot_queue_words -= word_count
                    model_lock.release()

            elif tts_hot_worker and _should_queue_hot(word_count):
                # ── Branch B: hot lane busy but cheaper to wait ───────────────────
                drain_est = (_hot_queue_words * _hot_ema_spw) if _hot_ema_spw else 0.0
                threshold = _get_cold_start_time() * HOT_QUEUE_SAFETY_FACTOR
                if DEBUG: print(f"--- ROUTER: Smart routing → queue hot lane. drain_est={drain_est:.1f}s < threshold={threshold:.1f}s. words={word_count} ---", flush=True)
                _hot_queue_words += word_count   # announce intent before waiting so late arrivals see full depth
                t0 = time.monotonic()
                try:
                    # _run_tts_hot_locked acquires, synthesizes, and releases the lock inside a
                    # single thread — safe against asyncio task cancellation (client timeout).
                    # A two-step acquire-then-release pattern deadlocks if a CancelledError fires
                    # between the two awaits, leaving the lock permanently acquired.
                    await asyncio.to_thread(_run_tts_hot_locked, req.input, lang, speaker_wav, req.speed, temp_wav, params)
                    _update_hot_ema(time.monotonic() - t0, word_count)
                finally:
                    _hot_queue_words -= word_count

            else:
                # ── Branch C: hot lane busy and cold lane is faster ───────────────
                global _cold_workers_in_flight
                free_gb = _free_vram_gb()
                vram_ok = _has_vram_for_cold_lane()
                if not vram_ok:
                    # Insufficient VRAM — skip cold subprocess entirely and queue hot directly.
                    # Avoids the ~10s wasted on a model load that will OOM mid-way.
                    print(f"--- ROUTER: Insufficient VRAM ({free_gb:.1f} GB free < {MIN_COLD_VRAM_GB} GB required) → queuing hot lane. words={word_count} ---", flush=True)
                    _hot_queue_words += word_count
                    t0 = time.monotonic()
                    try:
                        await asyncio.to_thread(_run_tts_hot_locked, req.input, lang, speaker_wav, req.speed, temp_wav, params)
                        _update_hot_ema(time.monotonic() - t0, word_count)
                    finally:
                        _hot_queue_words -= word_count
                else:
                    if DEBUG:
                        drain_est = (_hot_queue_words * _hot_ema_spw) if _hot_ema_spw else None
                        vram_str = f"{free_gb:.1f} GB free ({_cold_workers_in_flight} in-flight)" if free_gb is not None else "VRAM unknown"
                        if drain_est is not None:
                            print(f"--- ROUTER: Smart routing → cold lane. drain_est={drain_est:.1f}s ≥ threshold={_get_cold_start_time() * HOT_QUEUE_SAFETY_FACTOR:.1f}s. {vram_str}. words={word_count} ---", flush=True)
                        else:
                            print(f"--- ROUTER: EMA not calibrated → cold lane. {vram_str}. words={word_count} ---", flush=True)
                    _cold_workers_in_flight += 1
                    t_cold = time.monotonic()
                    try:
                        await run_tts_child_lane_async(req.input, lang, speaker_wav, req.speed, temp_wav, params)
                        _update_cold_ema(time.monotonic() - t_cold)
                    except Exception as cold_err:
                        print(f"--- ROUTER: Cold lane failed ({cold_err}). Falling back to hot lane queue. words={word_count} ---", flush=True)
                        _hot_queue_words += word_count
                        try:
                            # Note: EMA is NOT updated here — fallback elapsed includes cold-lane failure time.
                            await asyncio.to_thread(_run_tts_hot_locked, req.input, lang, speaker_wav, req.speed, temp_wav, params)
                        finally:
                            _hot_queue_words -= word_count
                    finally:
                        _cold_workers_in_flight -= 1

            convert_audio(temp_wav, final_output_path, req.response_format)

        except Exception as e:
            if DEBUG: print(f"[!] ERROR in create_speech: {str(e)}", flush=True)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if os.path.exists(temp_wav): os.remove(temp_wav)
            if custom_wav_path and os.path.exists(custom_wav_path): os.remove(custom_wav_path)

    return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")

# -------------------------------
# 7. Endpoint: POST /v1/audio/speech/stream
# -------------------------------

@app.post("/v1/audio/speech/stream")
async def create_speech_stream(request: Request):
    """
    Streaming TTS endpoint. Returns audio/wav with chunked transfer encoding.

    Uses XTTS-v2 inference_stream on the Hot Lane only.
    - If the hot worker is not loaded: HTTP 503.
    - If the hot worker is busy (lock taken): HTTP 503. Use /v1/audio/speech for queued synthesis.
    - No cache: audio is generated and sent in real time.
    - Output format: WAV (PCM 16-bit, mono, 24000 Hz). The response_format field is ignored.
    - custom_voice_file (multipart) is not supported on this endpoint.

    Accepts the same JSON / form-data fields as POST /v1/audio/speech.
    """
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        data = await request.json()
        req = SpeechRequest(**data)
    else:
        form_data = await request.form()
        req = SpeechRequest(
            input=form_data.get("input"),
            voice=form_data.get("voice", "alloy"),
            response_format="wav",  # streaming output is always WAV
            speed=float(form_data.get("speed", 1.0)),
            language=form_data.get("language", os.environ.get("DEFAULT_LANGUAGE", "en")),
            temperature=float(form_data.get("temperature", os.environ.get("DEFAULT_TEMPERATURE", 0.75))),
            length_penalty=float(form_data.get("length_penalty", os.environ.get("DEFAULT_LENGTH_PENALTY", 1.0))),
            repetition_penalty=float(form_data.get("repetition_penalty", os.environ.get("DEFAULT_REPETITION_PENALTY", 5.0))),
            top_k=int(form_data.get("top_k", os.environ.get("DEFAULT_TOP_K", 50))),
            top_p=float(form_data.get("top_p", os.environ.get("DEFAULT_TOP_P", 0.85)))
        )

    if not tts_hot_worker:
        raise HTTPException(status_code=503, detail="Hot worker not loaded. Streaming is unavailable.")

    if not model_lock.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Hot worker is busy. Retry or use /v1/audio/speech for queued synthesis.")

    v_file = VOICE_MAP.get(req.voice.lower(), VOICE_MAP["alloy"])
    speaker_wav = os.path.join(VOICE_ASSET_DIR, v_file)
    if not os.path.exists(speaker_wav):
        if DEBUG: print(f"[!] Voice file not found: {speaker_wav}. Falling back to alloy.", flush=True)
        speaker_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP["alloy"])

    lang = req.language
    params = {
        "temperature": req.temperature,
        "length_penalty": req.length_penalty,
        "repetition_penalty": req.repetition_penalty,
        "top_k": req.top_k,
        "top_p": req.top_p
    }

    if DEBUG: print(f"--- STREAM LANE: New request. voice={req.voice}, lang={lang} ---", flush=True)

    async def generate_and_release():
        """Wraps the stream generator and guarantees model_lock is released after streaming ends."""
        try:
            async for chunk in stream_tts_hot_lane_async(req.input, lang, speaker_wav, req.speed, params):
                yield chunk
        finally:
            model_lock.release()
            if DEBUG: print("--- STREAM LANE: Lock released. ---", flush=True)

    return StreamingResponse(generate_and_release(), media_type="audio/wav")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_tts:app", host="0.0.0.0", port=5100)
