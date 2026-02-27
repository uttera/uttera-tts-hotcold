#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Coqui TTS Server (Hybrid Model)
#
# Package: coqui-tts-server
# Version: 1.2.5
# Maintainer: Uttera, Hugo L. Espuny
# Description: High-performance TTS server with GPU acceleration, concurrency, and OpenAI API compliance.
#
# CHANGELOG:
# - 1.2.6 (2026-02-27): Dynamic language param, English default, and README architecture documentation.
# - 1.2.5 (2026-02-27): Default language set to 'en'. Full multilingual support.
# - 1.2.4 (2026-02-27): Added dynamic language parameter and cache integration.
# - 1.2.3 (2026-02-27): Added OpenAI JSON support, Stark Elite voice gallery, and multi-format conversion.

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
VENV_PYTHON = "/usr/local/lib/coqui/bin/python"
TTS_SCRIPT = "/usr/local/lib/coqui/bin/tts"
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"

# Storage Paths
AUDIO_CACHE_DIR = os.environ.get("AUDIO_CACHE_DIR", "/opt/ai/cache/coqui-tts-audio")
MODEL_CACHE_DIR = os.environ.get("TTS_HOME", "/opt/ai/models/speech/coqui-tts")
VOICE_ASSET_DIR = os.environ.get("VOICE_ASSET_DIR", "/opt/ai/assets/voices")

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
os.makedirs(MODEL_CACHE_DIR, exist_ok=True)

DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# --- Voice Mapping ---
VOICE_MAP = {
    "alloy": "standard/alloy.wav",
    "echo": "standard/echo.wav",
    "fable": "standard/fable.wav",
    "onyx": "standard/onyx.wav",
    "nova": "standard/nova.wav",
    "shimmer": "standard/shimmer.wav",
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
        warmup_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP["narrator"])
        if os.path.exists(warmup_wav):
            worker.tts("System online.", speaker_wav=warmup_wav, language="en")
        tts_hot_worker = worker
    except Exception as e:
        print(f"[!] ERROR: {e}")

# -------------------------------
# 3. OpenAI Schema Models
# -------------------------------
class SpeechRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str = "alloy"
    language: Optional[str] = "en"
    response_format: str = "mp3"
    speed: float = 1.0

app = FastAPI(title="Coqui TTS Server", version="1.2.5")

# -------------------------------
# 4. Core Logic
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
    subprocess.run(cmd, capture_output=True, check=True)

def run_tts_hot_lane(text: str, lang: str, speaker_wav: str, speed: float, output_path: str):
    tts_hot_worker.tts_to_file(text=text, speaker_wav=speaker_wav, language=lang, file_path=output_path, speed=speed)

def run_tts_cold_lane(text: str, lang: str, speaker_wav: str, speed: float, output_path: str):
    sub_env = os.environ.copy()
    sub_env["COQUI_TOS_AGREED"] = "1"
    cmd = [VENV_PYTHON, TTS_SCRIPT, "--text", text, "--model_name", MODEL_NAME, "--speaker_wav", speaker_wav, "--language_idx", lang, "--out_path", output_path, "--progress_bar", "False", "--use_cuda", "yes"]
    subprocess.run(cmd, capture_output=True, text=True, env=sub_env)

@app.post("/v1/audio/speech")
async def create_speech(request: Request, background_tasks: BackgroundTasks):
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        data = await request.json()
        req = SpeechRequest(**data)
        custom_wav_path = None
    else:
        form_data = await request.form()
        req = SpeechRequest(input=form_data.get("input"), voice=form_data.get("voice", "alloy"), language=form_data.get("language", "en"), response_format=form_data.get("response_format", "mp3"), speed=float(form_data.get("speed", 1.0)))
        custom_file = form_data.get("custom_voice_file")
        if custom_file and isinstance(custom_file, UploadFile):
            temp_custom = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_custom.write(await custom_file.read())
            temp_custom.close()
            custom_wav_path = temp_custom.name
        else: custom_wav_path = None

    if custom_wav_path:
        speaker_wav = custom_wav_path
        voice_id = hashlib.md5(custom_wav_path.encode()).hexdigest()
    else:
        v_file = VOICE_MAP.get(req.voice.lower(), VOICE_MAP["alloy"])
        speaker_wav = os.path.join(VOICE_ASSET_DIR, v_file)
        voice_id = req.voice.lower()
        if not os.path.exists(speaker_wav): speaker_wav = os.path.join(VOICE_ASSET_DIR, VOICE_MAP["alloy"])

    lang = req.language if req.language else "en"
    cache_key = hashlib.md5(f"{req.input}{voice_id}{req.speed}{req.response_format}{lang}".encode()).hexdigest()
    final_output_path = os.path.join(AUDIO_CACHE_DIR, f"{cache_key}.{req.response_format}")
    
    if os.path.exists(final_output_path): return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")

    temp_wav = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4()}.wav")
    try:
        if tts_hot_worker and model_lock.acquire(blocking=False):
            try: await asyncio.to_thread(run_tts_hot_lane, req.input, lang, speaker_wav, req.speed, temp_wav)
            finally: model_lock.release()
        else: await asyncio.to_thread(run_tts_cold_lane, req.input, lang, speaker_wav, req.speed, temp_wav)
        convert_audio(temp_wav, final_output_path, req.response_format)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_wav): os.remove(temp_wav)
        if custom_wav_path and os.path.exists(custom_wav_path): os.remove(custom_wav_path)

    return FileResponse(final_output_path, media_type=f"audio/{req.response_format}")

if __name__ == "__main__":
    load_hot_worker()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5100)
