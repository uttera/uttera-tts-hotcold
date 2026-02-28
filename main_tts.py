#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# main_tts.py - Coqui TTS Hybrid-Worker Server
# Copyright (C) 2025 Gemini (Author) & Hugo L. Espuny (Supervisor)
#
# Package: coqui-tts-server
# Version: 1.1.0
# Maintainer: Uttera, Hugo L. Espuny
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
#
# --- Architecture Summary ---
#
# This server implements a hybrid "hot/cold" worker model to provide
# true concurrent TTS synthesis from a single FastAPI instance.
#
# * MAIN LANE (Hot Worker):
#   An XTTSv2 model is pre-loaded into VRAM on startup ('tts_hot_worker')
#   and pre-heated with the default voice (voice-c).
#   It is protected by a threading.Lock ('model_lock') to prevent race
#   conditions, as the TTS object is not thread-safe.
#   It runs in a separate thread via asyncio.to_thread().
#
# * CHILD LANE (Cold Worker):
#   If the 'model_lock' is busy, the request is rerouted to the
#   'run_tts_child_lane' function.
#
# * Concurrency Solution (GIL Bypass):
#   The CHILD LANE is an 'async' function that uses
#   'await asyncio.create_subprocess_exec' to spawn a new
#   'tts' process. This new process is not blocked by the main
#   process's Global Interpreter Lock (GIL), allowing it to run in
#   true parallel.
#
# * Deadlock Fixes:
#   1. (License): The 'COQUI_TOS_AGREED=1' env var is passed to the
#      subprocess to prevent it from hanging on the [y/n] license prompt.
#   2. (Logs): 'await process.communicate()' is used to consume the
#      stdout/stderr pipes, preventing a buffer deadlock if the
#      subprocess is too verbose.
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
from typing import Optional, List, Union

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
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

VENV_PYTHON = os.environ.get("VENV_PYTHON", os.path.join(BASE_DIR, "venv/bin/python"))
TTS_SCRIPT = os.environ.get("TTS_SCRIPT", os.path.join(BASE_DIR, "venv/bin/tts"))
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"

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
# Each key points to a .wav reference file in VOICE_ASSET_DIR
VOICE_MAP = {
    # OpenAI Standard Mappings
    "alloy": "standard/alloy.wav",
    "echo": "standard/echo.wav",
    "fable": "standard/fable.wav",
    "onyx": "standard/onyx.wav",
    "nova": "standard/nova.wav",
    "shimmer": "standard/shimmer.wav",
    
    # Stark Elite Gallery
    "narrator": "elite/redacted-voice.wav",
    "voice-b": "elite/redacted-voice.wav",
    "voice-c": "elite/redacted-voice.wav",
    "voice-a": "elite/redacted-voice.wav",
    "voice-d": "elite/redacted.wav",
    "voice-e": "elite/redacted.wav",
    "voice-f": "elite/redacted.wav",
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
    if DEBUG: print(f"[*] Loading HOT WORKER model: {MODEL_NAME}")
    try:
        torch.backends.cudnn.benchmark = True
        worker = TTS(model_name=MODEL_NAME, progress_bar=False)
        worker.to("cuda")
        
        # Warm up with a silent reference or default
        warmup_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP["alloy"])
        if os.path.exists(warmup_wav):
            worker.tts("System online.", speaker_wav=warmup_wav, language="en")
            if DEBUG: print("[+] Hot worker warmed up and ready on GPU.")
        tts_hot_worker = worker
    except Exception as e:
        print(f"[!] CRITICAL ERROR: Failed to load hot worker: {e}")

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

app = FastAPI(title="Coqui TTS Server", version="1.1.0")

# -------------------------------
# 4. Core Logic: The Two Lanes
# -------------------------------

def convert_audio(input_path: str, output_path: str, fmt: str):
    """Converts WAV to requested format using ffmpeg."""
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
    subprocess.run(cmd, capture_output=True, check=True)

def run_tts_hot_lane(text: str, lang: str, speaker_wav: str, speed: float, output_path: str):
    if DEBUG: print(f"--- MAIN LANE: Using hot worker (GPU) ---")
    tts_hot_worker.tts_to_file(
        text=text,
        speaker_wav=speaker_wav,
        language=lang,
        file_path=output_path,
        speed=speed
    )

async def run_tts_cold_lane_async(text: str, lang: str, speaker_wav: str, speed: float, output_path: str):
    """
    CHILD LANE: Async subprocess execution to bypass GIL and prevent deadlocks.
    """
    if DEBUG: print(f"--- CHILD LANE: Spawning new cold worker... ---")
    sub_env = os.environ.copy()
    sub_env["COQUI_TOS_AGREED"] = "1"
    sub_env["TTS_HOME"] = MODEL_CACHE_DIR
    
    cmd = [
        VENV_PYTHON, TTS_SCRIPT,
        "--text", text,
        "--model_name", MODEL_NAME,
        "--speaker_wav", speaker_wav,
        "--language_idx", lang,
        "--out_path", output_path,
        "--progress_bar", "False",
        "--use_cuda", "yes"
    ]
    
    if DEBUG: print(f"DEBUG EXEC: {' '.join(cmd)}")
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=sub_env
    )
    
    # Wait for process to finish and consume pipes to prevent buffer deadlock
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        if DEBUG: print(f"[!] SUBPROCESS ERROR: {stderr.decode()}")
        raise Exception("Cold worker subprocess failed.")

# -------------------------------
# 5. Endpoint: POST /v1/audio/speech
# -------------------------------

@app.post("/v1/audio/speech")
async def create_speech(request: Request, background_tasks: BackgroundTasks):
    # Determine if input is JSON or Form
    content_type = request.headers.get("Content-Type", "")
    
    if "application/json" in content_type:
        data = await request.json()
        req = SpeechRequest(**data)
        custom_wav_path = None
    else:
        # Legacy/Advanced Form support
        form_data = await request.form()
        req = SpeechRequest(
            input=form_data.get("input"),
            voice=form_data.get("voice", "alloy"),
            response_format=form_data.get("response_format", "mp3"),
            speed=float(form_data.get("speed", 1.0))
        )
        # Check for dynamic cloning file
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
            if DEBUG: print(f"[!] Voice file not found: {speaker_wav}. Falling back to alloy.")
            speaker_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP["alloy"])

    # Language Detection (Default to 'es')
    lang = "es"

    # Cache Check
    cache_key = hashlib.md5(f"{req.input}{voice_id}{req.speed}{req.response_format}".encode()).hexdigest()
    final_output_path = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.{req.response_format}")
    
    if os.path.exists(final_output_path):
        if DEBUG: print(f"--- ROUTER: Cache hit for {cache_key} ---")
        return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")

    # Generation
    temp_wav = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4()}.wav")
    
    try:
        if tts_hot_worker and model_lock.acquire(blocking=False):
            if DEBUG: print("--- ROUTER: Fast lane is free. Sending request. ---")
            try:
                await asyncio.to_thread(run_tts_hot_lane, req.input, lang, speaker_wav, req.speed, temp_wav)
            finally:
                model_lock.release()
        else:
            if DEBUG: print("--- ROUTER: Main lane is busy. Rerouting to child lane. ---")
            # Using the ASYNC version of the cold lane from the reference architecture
            await run_tts_child_lane_async(req.input, lang, speaker_wav, req.speed, temp_wav)
        
        # Convert to requested format
        convert_audio(temp_wav, final_output_path, req.response_format)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_wav): os.remove(temp_wav)
        if custom_wav_path and os.path.exists(custom_wav_path): os.remove(custom_wav_path)

    return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_tts:app", host="0.0.0.0", port=5100)
