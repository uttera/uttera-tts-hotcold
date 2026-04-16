#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Hugo L. Espuny
#
# Part of the Uttera voice stack (https://uttera.ai).
# See LICENSE and NOTICE at the repository root.
"""
cold_worker_tts.py — Persistent subprocess for the cold worker pool.

Spawned by main_tts.py; stays alive to serve multiple synthesis requests
without paying the model-load cost each time (~30 s on XTTS-v2).

Loads the TTS backend selected by the TTS_BACKEND env var (default
'coqui') through the same plugin factory the hot lane uses. This means
cold workers automatically pick up new backends without touching this
file.

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
  TTS_BACKEND              — plugin name (default: "coqui")
  TTS_MODEL                — model name/path, consumed by the backend
  TTS_HOME                 — model cache directory
  COQUI_PRECISION          — "fp32", "fp16", or "bf16" (default: "fp32")
  COLD_WORKER_IDLE_TIMEOUT — idle seconds before exit (default: 60)
"""

import sys
import os
import json
import base64
import select
import warnings

warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")
warnings.filterwarnings("ignore", message=".*_register_pytree_node.*")

os.environ["COQUI_TOS_AGREED"] = "1"

# Imported after the env var and warning filters above — noqa: E402.
import torch  # noqa: E402

# Monkey-patch: numpy() does not support bf16; auto-convert to fp32.
_orig_numpy = torch.Tensor.numpy
def _bf16_safe_numpy(self, *args, **kwargs):
    if self.dtype == torch.bfloat16:
        return _orig_numpy(self.float(), *args, **kwargs)
    return _orig_numpy(self, *args, **kwargs)
torch.Tensor.numpy = _bf16_safe_numpy

# Monkey-patch: inject isin_mps_friendly if missing from transformers.
# Must run before the Coqui backend pulls in the transformers import chain.
try:
    from transformers.pytorch_utils import isin_mps_friendly  # noqa: F401
except ImportError:
    try:
        import transformers.pytorch_utils as _tpu
        def _isin_mps_friendly(elements, test_elements):
            return torch.isin(elements, test_elements)
        _tpu.isin_mps_friendly = _isin_mps_friendly
    except ImportError:
        # transformers not installed (non-Coqui backend) — nothing to patch.
        pass

# ── Config from env ────────────────────────────────────────────────────────────
COQUI_PRECISION = os.environ.get("COQUI_PRECISION", "fp32").lower().strip()
IDLE_TIMEOUT = float(os.environ.get("COLD_WORKER_IDLE_TIMEOUT", "60"))


def _write(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


# ── Backend loading ────────────────────────────────────────────────────────────
# Ensure the project root is on sys.path so `import backends` works when this
# script is launched from an absolute path by a systemd unit or similar.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from backends import load_backend  # noqa: E402

_backend = load_backend()
_device = "cuda" if torch.cuda.is_available() else "cpu"
_backend.load(device=_device, precision=COQUI_PRECISION)

_write({"ready": True})

# ── Request loop ───────────────────────────────────────────────────────────────
try:
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

        try:
            audio_bytes = _backend.infer(
                text=text,
                voice_wav_path=speaker_wav,
                language=language,
                speed=speed,
                params=params,
            )
            _write({"audio_b64": base64.b64encode(audio_bytes).decode()})
        except Exception as exc:
            _write({"error": str(exc)})
finally:
    try:
        _backend.unload()
    except Exception:
        pass
