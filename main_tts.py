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
# Version: 1.2.0
# Maintainer: Uttera, Hugo L. Espuny
# Description: High-performance TTS server with personality tuning and GIL-bypass concurrency.
#
# CHANGELOG:
# - 1.2.0 (2026-03-03): Added personality parameters, API parity for Cold Lane, and smart .env/venv detection.
# - 1.2.0 (2026-03-03): CLEANUP: Removed TTS_SCRIPT (deprecated) and added TTS_MODEL env support.
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
import asyncio
import hashlib
import tempfile
import subprocess
import threading
import warnings
import sys
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

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request, BackgroundTasks
from pydantic import BaseModel
from fastapi.responses import FileResponse, StreamingResponse
from TTS.api import TTS
import torch

# -------------------------------
# 1. Configuration & Paths
# -------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

# --- Voice Mapping: OpenAI Standards & Elite Gallery ---
VOICE_MAP = {
    "alloy": "standard/alloy.wav",
    "echo": "standard/echo.wav",
    "fable": "standard/fable.wav",
    "onyx": "standard/onyx.wav",
    "nova": "standard/nova.wav",
    "shimmer": "standard/shimmer.wav",
    
    "narrator": "elite/redacted-voice.wav",
    "assistant1": "elite/narrator.wav",
    "assistant2": "elite/assistant-1.wav",
    "voice-b": "elite/redacted-voice.wav",
    "voice-c": "elite/redacted-voice.wav",
    "hal1": "elite/voice-c.wav",
    "voice-a": "elite/redacted-voice.wav",
    "voice-d": "elite/redacted.wav",
    "voice-e": "elite/redacted.wav",
    "voice-f": "elite/redacted.wav",
    "tars1": "elite/voice-f-1.wav",
    "voice-g": "elite/redacted.wav",
    "voice-h": "elite/redacted.wav"
}

# -------------------------------
# 2. Concurrency & Model Loading
# -------------------------------
model_lock = threading.Lock()
tts_hot_worker = None

def load_hot_worker():
    global tts_hot_worker
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
        print(f"[!] CRITICAL ERROR: Failed to load hot worker: {e}", flush=True)

load_hot_worker()

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

app = FastAPI(title="Coqui TTS Server", version="1.2.0")

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
    
    subprocess.run(cmd, capture_output=(not DEBUG), check=True)

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
    
    # We use a python one-liner to maintain full API parity with the hot worker
    # including personality parameters which the 'tts' CLI does not support.
    python_code = f"""
from TTS.api import TTS
import os
os.environ['COQUI_TOS_AGREED'] = '1'
model_name = "{MODEL_NAME}"
tts = TTS(model_name=model_name, progress_bar=False)
tts.to("cuda")
tts.tts_to_file(
    text=\"\"\"{text}\"\"\",
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
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        if DEBUG: print(f"[!] Cold worker failed: {stderr.decode()}", flush=True)
        raise Exception(f"Cold worker subprocess failed (code {process.returncode})")

# -------------------------------
# 5. Endpoint: POST /v1/audio/speech
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
    
    if os.path.exists(final_output_path):
        if DEBUG: print(f"--- ROUTER: Cache hit for {cache_key} ---", flush=True)
        return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")

    temp_wav = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4()}.wav")
    try:
        if tts_hot_worker and model_lock.acquire(blocking=False):
            if DEBUG: print("--- ROUTER: Fast lane is free. Sending request. ---", flush=True)
            try:
                await asyncio.to_thread(run_tts_hot_lane, req.input, lang, speaker_wav, req.speed, temp_wav, params)
            finally:
                model_lock.release()
        else:
            if DEBUG: print("--- ROUTER: Main lane is busy. Rerouting to child lane. ---", flush=True)
            await run_tts_child_lane_async(req.input, lang, speaker_wav, req.speed, temp_wav, params)
        
        convert_audio(temp_wav, final_output_path, req.response_format)
        
    except Exception as e:
        if DEBUG: print(f"[!] ERROR in create_speech: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_wav): os.remove(temp_wav)
        if custom_wav_path and os.path.exists(custom_wav_path): os.remove(custom_wav_path)

    return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_tts:app", host="0.0.0.0", port=5100)
