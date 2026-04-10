#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cold_worker_tts.py — Persistent XTTS-v2 subprocess for the cold worker pool.

Spawned by main_tts.py and stays alive to serve multiple synthesis requests
without paying the model-load cost each time (~30 s on XTTS-v2).

Protocol (newline-delimited JSON on stdin/stdout):

  Startup
    Worker writes {"ready": true} when the model is fully loaded.

  Request (parent → worker, one JSON line)
    {"text": "...", "speaker_wav": "/abs/path/to/speaker.wav",
     "language": "es", "speed": 1.0,
     "temperature": 0.75, "length_penalty": 1.0,
     "repetition_penalty": 5.0, "top_k": 50, "top_p": 0.85}

  Response (worker → parent, one JSON line)
    {"audio_b64": "<base64 WAV bytes>"}   — successful synthesis
    {"error": "..."}                       — synthesis failed; worker still alive

  Shutdown
    Parent writes {"exit": true}  — clean shutdown
    Parent closes stdin (EOF)     — clean shutdown
    Idle timeout expires          — worker writes {"exit": "idle_timeout"} and exits

Environment variables (set by main_tts.py at spawn time):
  TTS_MODEL                — model name (default: tts_models/multilingual/multi-dataset/xtts_v2)
  TTS_HOME                 — model cache directory
  COQUI_FP16               — "1" to use fp16+LN-fp32, "0" for fp32 (default: "1")
  COLD_WORKER_IDLE_TIMEOUT — idle seconds before exit (default: 60)
"""

import sys
import os
import json
import base64
import tempfile
import select
import warnings

warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")
warnings.filterwarnings("ignore", message=".*_register_pytree_node.*")

os.environ["COQUI_TOS_AGREED"] = "1"

import torch

# Monkey-patch: inject isin_mps_friendly if missing from transformers.
# Must run before TTS import triggers the transformers import chain.
try:
    from transformers.pytorch_utils import isin_mps_friendly  # noqa: F401
except ImportError:
    import transformers.pytorch_utils as _tpu
    def _isin_mps_friendly(elements, test_elements):
        return torch.isin(elements, test_elements)
    _tpu.isin_mps_friendly = _isin_mps_friendly

from TTS.api import TTS

# ── Config from env ────────────────────────────────────────────────────────────
MODEL_NAME = os.environ.get("TTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
MODEL_CACHE_DIR = os.environ.get("TTS_HOME", "assets/models")
_fp16_env = os.environ.get("COQUI_FP16", "1").lower()
COQUI_FP16 = _fp16_env in ("1", "true", "yes")
IDLE_TIMEOUT = float(os.environ.get("COLD_WORKER_IDLE_TIMEOUT", "60"))


def _write(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


# ── Model loading ──────────────────────────────────────────────────────────────
_cuda = torch.cuda.is_available()
_use_fp16 = _cuda and COQUI_FP16

tts = TTS(model_name=MODEL_NAME, progress_bar=False)
tts.to("cuda" if _cuda else "cpu")

if _use_fp16:
    # fp16 weights + LayerNorm in fp32 for numerical stability (same pattern as whisper).
    # Halves VRAM footprint: ~3.5 GB (fp32) → ~1.75 GB (fp16) per worker.
    tts.synthesizer.tts_model = tts.synthesizer.tts_model.half()
    for _m in tts.synthesizer.tts_model.modules():
        if isinstance(_m, torch.nn.LayerNorm):
            _m.float()

_write({"ready": True})

# ── Request loop ───────────────────────────────────────────────────────────────
while True:
    ready, _, _ = select.select([sys.stdin], [], [], IDLE_TIMEOUT)
    if not ready:
        _write({"exit": "idle_timeout"})
        break

    line = sys.stdin.readline()
    if not line:  # EOF — parent closed stdin
        break

    req = json.loads(line.strip())
    if req.get("exit"):
        break

    text = req["text"]
    speaker_wav = req["speaker_wav"]
    language = req.get("language", "en")
    speed = float(req.get("speed", 1.0))
    params = {
        "temperature":        float(req.get("temperature", 0.75)),
        "length_penalty":     float(req.get("length_penalty", 1.0)),
        "repetition_penalty": float(req.get("repetition_penalty", 5.0)),
        "top_k":              int(req.get("top_k", 50)),
        "top_p":              float(req.get("top_p", 0.85)),
    }

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            temp_path = f.name

        # autocast resolves fp32/fp16 type mismatches (speaker conditioning computes
        # in fp32; autocast casts inputs to fp16 to match the converted model weights).
        with torch.autocast("cuda", dtype=torch.float16, enabled=_use_fp16):
            tts.tts_to_file(
                text=text,
                speaker_wav=speaker_wav,
                language=language,
                file_path=temp_path,
                speed=speed,
                **params,
            )

        with open(temp_path, "rb") as f:
            audio_bytes = f.read()

        _write({"audio_b64": base64.b64encode(audio_bytes).decode()})
    except Exception as exc:
        _write({"error": str(exc)})
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
