#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Hugo L. Espuny
# Original work created with assistance from Google Gemini and Anthropic Claude
#
# Part of the Uttera voice stack (https://uttera.ai).
# See LICENSE and NOTICE at the repository root.
"""
backends/voxcpm_backend.py — VoxCPM2 adapter for hot/cold pool architecture.

Wraps the voxcpm library (plain, NOT nano-vllm) as a `TTSBackend`
implementation. Designed for consumer GPUs where keeping the model
resident 24/7 is not desirable — the hot/cold pool loads and unloads
workers dynamically.

VoxCPM2 is a 2B-param tokenizer-free diffusion autoregressive model
supporting 30 languages at 48 kHz output. Licensed under Apache-2.0 —
commercial use is permitted without restriction.

Personality parameters:
  - cfg_value (classifier-free guidance): controls how closely the
    output follows the reference voice and text conditioning. Default
    2.0. Higher = more faithful; lower = more creative. Passed via
    params["cfg_value"] or mapped from params["temperature"] if
    cfg_value is not present.
  - inference_timesteps: diffusion steps. Default 10. More = better
    quality but slower. Passed via params["inference_timesteps"].

Parameters specific to Coqui (top_k, top_p, length_penalty,
repetition_penalty) are silently ignored — VoxCPM2 is diffusion-based,
not autoregressive token sampling.
"""
from __future__ import annotations

import io
import os
import struct
import sys
from typing import Iterator

from backends.base import TTSBackend


def print_err(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    kwargs.setdefault("flush", True)
    print(*args, **kwargs)


# VoxCPM2 supported languages (30, from OpenBMB model card).
VOXCPM2_LANGUAGES = [
    "en", "zh", "de", "fr", "ja", "ko", "es", "pt", "ru", "nl",
    "it", "pl", "tr", "cs", "ar", "hu", "el", "ro", "sv", "da",
    "fi", "no", "sk", "bg", "uk", "sr", "hr", "sl", "lt", "lv",
]

# Output sample rate for VoxCPM2 (fixed by the model's audio VAE).
VOXCPM2_SAMPLE_RATE = 48000

# Streaming WAV header (48 kHz mono 16-bit PCM, unknown length).
_STREAM_CHANNELS = 1
_STREAM_BITS = 16


def _make_streaming_wav_header() -> bytes:
    data_size = 0xFFFFFFFF
    riff_size = data_size + 36
    byte_rate = VOXCPM2_SAMPLE_RATE * _STREAM_CHANNELS * _STREAM_BITS // 8
    block_align = _STREAM_CHANNELS * _STREAM_BITS // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", riff_size, b"WAVE",
        b"fmt ", 16,
        1, _STREAM_CHANNELS, VOXCPM2_SAMPLE_RATE,
        byte_rate, block_align, _STREAM_BITS,
        b"data", data_size,
    )


class Backend(TTSBackend):
    """VoxCPM2 backend for hot/cold TTS serving."""

    name = "voxcpm"
    supports_streaming = True

    DEFAULT_MODEL = "openbmb/VoxCPM2"
    DEFAULT_CFG_VALUE = 2.0
    DEFAULT_INFERENCE_TIMESTEPS = 10

    def __init__(self) -> None:
        self._model = None
        self._model_id: str = os.environ.get("VOXCPM_MODEL", self.DEFAULT_MODEL)
        self._inference_timesteps: int = int(
            os.environ.get("VOXCPM_INFERENCE_TIMESTEPS", str(self.DEFAULT_INFERENCE_TIMESTEPS))
        )
        self._device: str = "cuda"
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # TTSBackend contract
    # ------------------------------------------------------------------

    def load(self, device: str = "cuda", precision: str = "fp32") -> None:
        """Load VoxCPM2 model from HuggingFace or local path."""
        import torch
        from huggingface_hub import snapshot_download

        if device.startswith("cuda") and not torch.cuda.is_available():
            print_err("VOXCPM BACKEND: CUDA unavailable — falling back to CPU.")
            device = "cpu"

        # Download model if not a local path
        if os.path.isdir(self._model_id):
            model_path = self._model_id
        else:
            print_err(f"VOXCPM BACKEND: downloading {self._model_id} from HuggingFace...")
            model_path = snapshot_download(repo_id=self._model_id)

        print_err(f"VOXCPM BACKEND: loading from {model_path} on {device}...")

        from voxcpm.model.voxcpm import VoxCPMModel
        self._model = VoxCPMModel.from_local(model_path, optimize=True)
        self._model = self._model.to(device)

        self._device = device
        self._loaded = True
        print_err("VOXCPM BACKEND: ready.")

    def infer(
        self,
        text: str,
        voice_wav_path: str | None,
        language: str,
        speed: float = 1.0,
        params: dict | None = None,
    ) -> bytes:
        """Synthesize text to WAV bytes (48 kHz mono 16-bit PCM)."""
        import soundfile as sf
        import numpy as np

        if not self._loaded or self._model is None:
            raise RuntimeError("VoxCPM backend: infer() called before load().")
        if not text or not text.strip():
            raise ValueError("VoxCPM backend: input text is empty.")

        p = params or {}
        cfg_value = p.get("cfg_value", self._resolve_cfg(p))
        timesteps = int(p.get("inference_timesteps", self._inference_timesteps))

        audio_tensor = self._model.generate(
            target_text=text,
            prompt_wav_path=voice_wav_path or "",
            cfg_value=cfg_value,
            inference_timesteps=timesteps,
        )

        # Convert tensor to WAV bytes
        audio_np = audio_tensor.cpu().numpy().astype(np.float32)
        if audio_np.ndim > 1:
            audio_np = audio_np.squeeze()

        buf = io.BytesIO()
        sf.write(buf, audio_np, VOXCPM2_SAMPLE_RATE, format="WAV")
        buf.seek(0)
        return buf.read()

    def infer_stream(
        self,
        text: str,
        voice_wav_path: str | None,
        language: str,
        speed: float = 1.0,
        params: dict | None = None,
    ) -> Iterator[bytes]:
        """Stream VoxCPM2 synthesis as WAV header + int16 PCM chunks."""
        import torch

        if not self._loaded or self._model is None:
            raise RuntimeError("VoxCPM backend: infer_stream() called before load().")
        if not text or not text.strip():
            raise ValueError("VoxCPM backend: input text is empty.")

        p = params or {}
        cfg_value = p.get("cfg_value", self._resolve_cfg(p))
        timesteps = int(p.get("inference_timesteps", self._inference_timesteps))

        yield _make_streaming_wav_header()

        for chunk_tensor in self._model.generate_streaming(
            target_text=text,
            prompt_wav_path=voice_wav_path or "",
            cfg_value=cfg_value,
            inference_timesteps=timesteps,
        ):
            audio_np = chunk_tensor.squeeze().cpu()
            pcm = (audio_np * 32767).to(torch.int16).numpy().tobytes()
            yield pcm

    def unload(self) -> None:
        """Release model and free VRAM. Idempotent."""
        if not self._loaded:
            return
        try:
            del self._model
        except Exception:
            pass
        self._model = None
        self._loaded = False
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def supported_languages(self) -> list[str]:
        """Return the 30 VoxCPM2 language codes."""
        return list(VOXCPM2_LANGUAGES)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_cfg(self, params: dict) -> float:
        """Map Coqui-style temperature to VoxCPM cfg_value if no explicit
        cfg_value was given.

        Heuristic: Coqui temperature 0.75 (default) → cfg_value 2.0 (default).
        Higher temperature (more random) → lower cfg (less conditioning).
        Lower temperature (more deterministic) → higher cfg.

        Formula: cfg = 3.5 - temperature * 2.0
          - temp=0.50 → cfg=2.5 (very conditioned)
          - temp=0.75 → cfg=2.0 (balanced, default)
          - temp=1.00 → cfg=1.5 (more creative)
          - temp=1.50 → cfg=0.5 (very creative)

        Clamped to [0.5, 5.0] for safety.
        """
        temperature = float(params.get("temperature", 0.75))
        cfg = 3.5 - temperature * 2.0
        return max(0.5, min(5.0, cfg))
