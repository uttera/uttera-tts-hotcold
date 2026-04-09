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
# main_tts.py - Coqui TTS Hybrid-Worker Server
# Copyright (C) 2025 Gemini (Author) & Hugo L. Espuny (Supervisor)
#
# Package: coqui-tts-server
# Version: 1.6.0
# Maintainer: Uttera, Hugo L. Espuny
# Description: High-performance TTS server with personality tuning and GIL-bypass concurrency.
#
# CHANGELOG:
# - 1.6.0 (2026-04-09): Shared work queue + persistent cold worker pool. Replaces the
#   Branch A/B/C spawn-and-die architecture (v1.5.x) with a persistent pool of XTTS-v2
#   subprocesses that serve multiple requests without reloading the model (~30 s saved
#   per request after the first). All synthesis requests enqueue to a single asyncio.Queue
#   consumed by the hot worker and all pool workers in parallel. Pool size is computed
#   dynamically every 0.5 s via _optimal_cold_workers() using the live queue depth (words)
#   and EMAs. Idle workers wind down with staggered timeouts (first spawned lives longest).
#   Cold EMA warmup at startup: a real synthesis runs through a fresh cold worker to measure
#   startup time and VRAM cost, then kills the worker before entering steady state.
#   Added COQUI_FP16=1 (default): fp16+LN-fp32 halves VRAM per worker (~3.5→~1.75 GB).
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
# --- Architecture Summary (v1.6.0) ---
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
# * STREAM LANE (unchanged)
#   POST /v1/audio/speech/stream uses XTTS-v2 inference_stream on the hot worker.
#   Acquires model_lock directly; returns HTTP 503 if busy.
#

import os
import io
import time
import uuid
import shutil
import struct
import asyncio
import hashlib
import tempfile
import threading
import dataclasses
import warnings
import sys
import json
import base64
import subprocess
from contextlib import asynccontextmanager
from typing import Optional, Set
from dotenv import load_dotenv

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

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request, BackgroundTasks
from pydantic import BaseModel
from fastapi.responses import FileResponse, StreamingResponse
from TTS.api import TTS
import torch

# -------------------------------
# 1. Global Config
# -------------------------------
PARENT_DIR = os.path.dirname(BASE_DIR)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

def find_venv_path(rel_path):
    local = os.path.join(BASE_DIR, rel_path)
    parent = os.path.join(PARENT_DIR, rel_path)
    if os.path.exists(local): return local
    if os.path.exists(parent): return parent
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

# fp16 for hot and cold workers. Halves VRAM: ~3.5 GB → ~1.75 GB per worker.
_fp16_env = os.environ.get("COQUI_FP16", "1").lower()
COQUI_FP16 = _fp16_env in ("1", "true", "yes")

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

SERVER_VERSION = "1.6.0"

# -------------------------------
# 2. Voice Mapping
# -------------------------------
VOICE_MAP = {
    "alloy":    "standard/alloy.wav",
    "echo":     "standard/echo.wav",
    "fable":    "standard/fable.wav",
    "onyx":     "standard/onyx.wav",
    "nova":     "standard/nova.wav",
    "shimmer":  "standard/shimmer.wav",
    "narrator":   "elite/narrator.wav",
    "voice-b":   "elite/redacted-voice.wav",
    "voice-c":      "elite/redacted-voice.wav",
    "voice-a": "elite/redacted-voice.wav",
    "voice-d":  "elite/redacted.wav",
    "voice-e":   "elite/redacted.wav",
    "voice-f":     "elite/redacted.wav",
    "voice-g":     "elite/redacted.wav",
    "voice-h":   "elite/redacted.wav",
}

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

# -------------------------------
# 4. Hot Model Loading
# -------------------------------
model_lock = threading.Lock()   # Serializes hot worker + streaming endpoint
tts_hot_worker = None
hot_worker_error: Optional[str] = None

def _load_hot_model():
    """Load XTTS-v2 and optionally convert to fp16. Called once at startup."""
    global tts_hot_worker, hot_worker_error
    print(f"HOT WORKER: Loading {MODEL_NAME}...", flush=True)
    try:
        torch.backends.cudnn.benchmark = True
        worker = TTS(model_name=MODEL_NAME, progress_bar=False)
        worker.to("cuda" if torch.cuda.is_available() else "cpu")
        if COQUI_FP16 and torch.cuda.is_available():
            worker.synthesizer.tts_model = worker.synthesizer.tts_model.half()
            for _m in worker.synthesizer.tts_model.modules():
                if isinstance(_m, torch.nn.LayerNorm):
                    _m.float()
            print("HOT WORKER: fp16 applied (LN in fp32).", flush=True)
        tts_hot_worker = worker
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
    effective = free - (_cold_workers_in_flight * threshold)
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

    async def spawn(self) -> bool:
        """Spawn the subprocess and wait for {"ready": true}. Returns False on failure."""
        env = os.environ.copy()
        env["TTS_MODEL"]                = MODEL_NAME
        env["TTS_HOME"]                 = MODEL_CACHE_DIR
        env["COQUI_FP16"]               = "1" if COQUI_FP16 else "0"
        env["COLD_WORKER_IDLE_TIMEOUT"] = str(COLD_WORKER_IDLE_TIMEOUT)
        env["COQUI_TOS_AGREED"]         = "1"
        try:
            self._proc = await asyncio.create_subprocess_exec(
                VENV_PYTHON, COLD_WORKER_TTS_SCRIPT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
            # Wait for {"ready": true}
            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=120.0)
            msg = json.loads(line.strip())
            return bool(msg.get("ready"))
        except Exception as e:
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

        response_line = await self._proc.stdout.readline()
        resp = json.loads(response_line.strip())
        if "error" in resp:
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
        top_p=params.get("top_p", 0.85),
    )


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
    Wakes every COLD_POOL_MANAGER_INTERVAL seconds.
    """
    while True:
        await asyncio.sleep(COLD_POOL_MANAGER_INTERVAL)

        target = _optimal_cold_workers()
        active = len(_pool_worker_tasks)
        loading = _cold_workers_in_flight

        if active + loading >= target:
            continue
        if _cold_spawn_lock is None or _cold_spawn_lock.locked():
            continue
        if not _has_vram_for_cold_lane():
            continue

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
            print(
                f"--- POOL MGR: pool worker ready, total_active={len(_pool_worker_tasks)}"
                f", idle_timeout={worker_idle_timeout:.0f}s ---",
                flush=True,
            )
        except Exception as e:
            print(f"--- POOL MGR: spawn failed: {e} ---", flush=True)

# -------------------------------
# 10. Startup Warmup
# -------------------------------
async def _warmup_hot_ema() -> None:
    """Seed _hot_ema_spw via a real synthesis through the hot lane."""
    if tts_hot_worker is None:
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
    global _work_queue, _cold_spawn_lock

    _work_queue = asyncio.Queue()
    _cold_spawn_lock = asyncio.Lock()

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


app = FastAPI(title="Coqui TTS Server", version=SERVER_VERSION, lifespan=_lifespan)

# -------------------------------
# 11. Audio Utilities
# -------------------------------
def convert_audio(input_path: str, output_path: str, fmt: str):
    if fmt == "wav":
        shutil.copy(input_path, output_path)
        return
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if fmt == "mp3":   cmd.extend(["-codec:a", "libmp3lame", "-qscale:a", "2"])
    elif fmt == "opus": cmd.extend(["-codec:a", "libopus", "-b:a", "64k"])
    elif fmt == "flac": cmd.extend(["-codec:a", "flac"])
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
            {"id": "tts-1",    "object": "model", "created": 1677610602, "owned_by": "uttera-legacy"},
            {"id": "tts-1-hd", "object": "model", "created": 1677610602, "owned_by": "uttera-legacy"},
        ],
    }

@app.get("/v1/voices")
async def list_voices():
    return {"voices": sorted(list(VOICE_MAP.keys()))}

@app.get("/health")
async def health_check():
    _free = _free_vram_gb()
    vram_per = _cold_vram_ema_gb if _cold_vram_ema_gb is not None else MIN_COLD_VRAM_GB
    return {
        "status": "ok",
        "version": SERVER_VERSION,
        "model": MODEL_NAME,
        "fp16": COQUI_FP16,
        "hot_worker_loaded": tts_hot_worker is not None,
        "hot_worker_error": hot_worker_error,
        "smart_routing": {
            "ema_spw": round(_hot_ema_spw, 4) if _hot_ema_spw is not None else None,
            "cold_ema_start_seconds": round(_cold_ema_start, 2) if _cold_ema_start is not None else None,
            "cold_start_calibrated": _cold_ema_start is not None,
            "cold_pool_size": len(_pool_worker_tasks),
            "cold_pool_loading": _cold_workers_in_flight,
            "cold_vram_ema_gb": round(_cold_vram_ema_gb, 2) if _cold_vram_ema_gb is not None else None,
            "vram_free_gb": round(_free, 2) if _free is not None else None,
            "queue_words": _work_queue_words,
        },
    }

# -------------------------------
# 13. Endpoint: POST /v1/audio/speech
# -------------------------------
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
            top_p=float(form_data.get("top_p", os.environ.get("DEFAULT_TOP_P", 0.85))),
        )
        custom_file = form_data.get("custom_voice_file")
        if custom_file and isinstance(custom_file, UploadFile):
            temp_custom = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_custom.write(await custom_file.read())
            temp_custom.close()
            custom_wav_path = temp_custom.name
        else:
            custom_wav_path = None

    # Resolve speaker WAV
    if custom_wav_path:
        speaker_wav = custom_wav_path
        voice_id = hashlib.md5(custom_wav_path.encode()).hexdigest()
    else:
        v_file = VOICE_MAP.get(req.voice.lower(), VOICE_MAP["alloy"])
        speaker_wav = os.path.join(VOICE_ASSET_DIR, v_file)
        voice_id = req.voice.lower()
        if not os.path.exists(speaker_wav):
            speaker_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP["alloy"])

    params = {
        "temperature":        req.temperature,
        "length_penalty":     req.length_penalty,
        "repetition_penalty": req.repetition_penalty,
        "top_k":              req.top_k,
        "top_p":              req.top_p,
    }
    cache_key = hashlib.md5(
        f"{req.input}{voice_id}{req.speed}{req.response_format}"
        f"{req.temperature}{req.length_penalty}{req.repetition_penalty}{req.top_k}{req.top_p}".encode()
    ).hexdigest()
    final_output_path = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.{req.response_format}")

    cache_lock = _cache_locks.setdefault(cache_key, asyncio.Lock())
    async with cache_lock:
        # Cache check — hits bypass the queue entirely
        if os.path.exists(final_output_path):
            if CACHE_TTL_MINUTES > 0:
                age_min = (time.time() - os.path.getmtime(final_output_path)) / 60
                if age_min < CACHE_TTL_MINUTES:
                    return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")
                os.remove(final_output_path)
            else:
                return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")

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

        try:
            audio_bytes, route = await future
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if custom_wav_path and os.path.exists(custom_wav_path):
                os.unlink(custom_wav_path)

        # Write WAV to temp, convert to target format, cache
        temp_wav = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4()}.wav")
        try:
            with open(temp_wav, "wb") as f:
                f.write(audio_bytes)
            convert_audio(temp_wav, final_output_path, req.response_format)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if os.path.exists(temp_wav):
                os.unlink(temp_wav)

    response = FileResponse(final_output_path, media_type=f"audio/{req.response_format}")
    response.headers["X-Route"] = route
    return response

# -------------------------------
# 14. Endpoint: POST /v1/audio/speech/stream  (unchanged — hot lane only)
# -------------------------------

_STREAM_SAMPLE_RATE    = 24000
_STREAM_NUM_CHANNELS   = 1
_STREAM_BITS_PER_SAMPLE = 16


def make_streaming_wav_header() -> bytes:
    data_size  = 0xFFFFFFFF
    riff_size  = data_size + 36
    byte_rate  = _STREAM_SAMPLE_RATE * _STREAM_NUM_CHANNELS * _STREAM_BITS_PER_SAMPLE // 8
    block_align = _STREAM_NUM_CHANNELS * _STREAM_BITS_PER_SAMPLE // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", riff_size, b"WAVE",
        b"fmt ", 16,
        1, _STREAM_NUM_CHANNELS, _STREAM_SAMPLE_RATE,
        byte_rate, block_align, _STREAM_BITS_PER_SAMPLE,
        b"data", data_size,
    )


async def stream_tts_hot_lane_async(text: str, lang: str, speaker_wav: str,
                                     speed: float, params: dict):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def sync_produce():
        try:
            gpt_cond_latent, speaker_embedding = (
                tts_hot_worker.synthesizer.tts_model.get_conditioning_latents(
                    audio_path=[speaker_wav]
                )
            )
            for chunk in tts_hot_worker.synthesizer.tts_model.inference_stream(
                text, lang, gpt_cond_latent, speaker_embedding,
                speed=speed,
                temperature=params.get("temperature", 0.75),
                length_penalty=params.get("length_penalty", 1.0),
                repetition_penalty=params.get("repetition_penalty", 5.0),
                top_k=params.get("top_k", 50),
                top_p=params.get("top_p", 0.85),
                stream_chunk_size=20,
            ):
                pcm_bytes = (chunk.squeeze() * 32767).to(torch.int16).cpu().numpy().tobytes()
                asyncio.run_coroutine_threadsafe(queue.put(pcm_bytes), loop).result()
        except Exception as e:
            asyncio.run_coroutine_threadsafe(queue.put(e), loop).result()
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    yield make_streaming_wav_header()
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
        req = SpeechRequest(**data)
    else:
        form_data = await request.form()
        req = SpeechRequest(
            input=form_data.get("input"),
            voice=form_data.get("voice", "alloy"),
            response_format="wav",
            speed=float(form_data.get("speed", 1.0)),
            language=form_data.get("language", os.environ.get("DEFAULT_LANGUAGE", "en")),
            temperature=float(form_data.get("temperature", os.environ.get("DEFAULT_TEMPERATURE", 0.75))),
            length_penalty=float(form_data.get("length_penalty", os.environ.get("DEFAULT_LENGTH_PENALTY", 1.0))),
            repetition_penalty=float(form_data.get("repetition_penalty", os.environ.get("DEFAULT_REPETITION_PENALTY", 5.0))),
            top_k=int(form_data.get("top_k", os.environ.get("DEFAULT_TOP_K", 50))),
            top_p=float(form_data.get("top_p", os.environ.get("DEFAULT_TOP_P", 0.85))),
        )

    if not tts_hot_worker:
        raise HTTPException(status_code=503, detail="Hot worker not loaded. Streaming unavailable.")
    if not model_lock.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Hot worker busy. Use /v1/audio/speech for queued synthesis.")

    v_file = VOICE_MAP.get(req.voice.lower(), VOICE_MAP["alloy"])
    speaker_wav = os.path.join(VOICE_ASSET_DIR, v_file)
    if not os.path.exists(speaker_wav):
        speaker_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP["alloy"])

    params = {
        "temperature": req.temperature, "length_penalty": req.length_penalty,
        "repetition_penalty": req.repetition_penalty, "top_k": req.top_k, "top_p": req.top_p,
    }

    async def generate_and_release():
        try:
            async for chunk in stream_tts_hot_lane_async(req.input, req.language, speaker_wav, req.speed, params):
                yield chunk
        finally:
            model_lock.release()

    return StreamingResponse(generate_and_release(), media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_tts:app", host="0.0.0.0", port=5100)
