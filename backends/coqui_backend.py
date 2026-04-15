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
backends/coqui_backend.py — Coqui TTS adapter (XTTS-v2 and friends).

Wraps the Coqui TTS library as a `TTSBackend` implementation. This is the
reference backend and the default when `TTS_BACKEND` is unset.

The Coqui XTTS-v2 model weights are distributed under the Coqui Public
Model License (CPML), which restricts use to non-commercial purposes.
See NOTICE at the repository root for details and commercial alternatives.
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
from typing import Iterator

from backends.base import TTSBackend


def print_err(*args, **kwargs):
    """Log to stderr so cold workers do not corrupt the stdout JSON protocol."""
    kwargs.setdefault("file", sys.stderr)
    kwargs.setdefault("flush", True)
    print(*args, **kwargs)


# XTTS-v2 language codes. Static list — see Coqui docs.
XTTS_V2_LANGUAGES = [
    "en", "es", "fr", "de", "it", "pt", "pl", "tr",
    "ru", "nl", "cs", "ar", "zh-cn", "hu", "ko", "ja",
]

# Streaming WAV header constants (XTTS-v2 outputs 24 kHz mono 16-bit PCM).
_STREAM_SAMPLE_RATE = 24000
_STREAM_NUM_CHANNELS = 1
_STREAM_BITS_PER_SAMPLE = 16


def _make_streaming_wav_header() -> bytes:
    """WAV header with the data-size field set to 0xFFFFFFFF (unknown length),
    safe for streaming HTTP responses."""
    data_size = 0xFFFFFFFF
    riff_size = data_size + 36
    byte_rate = (
        _STREAM_SAMPLE_RATE
        * _STREAM_NUM_CHANNELS
        * _STREAM_BITS_PER_SAMPLE
        // 8
    )
    block_align = _STREAM_NUM_CHANNELS * _STREAM_BITS_PER_SAMPLE // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", riff_size, b"WAVE",
        b"fmt ", 16,
        1, _STREAM_NUM_CHANNELS, _STREAM_SAMPLE_RATE,
        byte_rate, block_align, _STREAM_BITS_PER_SAMPLE,
        b"data", data_size,
    )


class Backend(TTSBackend):
    """Coqui TTS backend. Supports streaming for XTTS-v2-family models."""

    name = "coqui"
    supports_streaming = True

    #: Default Coqui model path. Overridden by the TTS_MODEL env var.
    DEFAULT_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

    def __init__(self) -> None:
        self._worker = None          # coqui TTS.api.TTS instance
        self._model_name: str = os.environ.get("TTS_MODEL", self.DEFAULT_MODEL)
        self._precision: str = "fp32"
        self._device: str = "cuda"
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # TTSBackend contract
    # ------------------------------------------------------------------

    def load(self, device: str = "cuda", precision: str = "fp32") -> None:
        """Load the Coqui model into memory and optionally convert precision."""
        import torch
        from TTS.api import TTS

        if precision not in ("fp32", "fp16", "bf16"):
            raise ValueError(
                f"Coqui backend: precision must be fp32, fp16, or bf16 "
                f"(got '{precision}')."
            )
        if device.startswith("cuda") and not torch.cuda.is_available():
            print_err(
                "COQUI BACKEND: CUDA requested but unavailable — falling "
                "back to CPU.",
                flush=True,
            )
            device = "cpu"

        print_err(f"COQUI BACKEND: loading {self._model_name} on {device}...", flush=True)
        torch.backends.cudnn.benchmark = True

        worker = TTS(model_name=self._model_name, progress_bar=False)
        worker.to(device)

        if precision != "fp32" and device.startswith("cuda"):
            if precision == "fp16":
                worker.synthesizer.tts_model = worker.synthesizer.tts_model.half()
                # LayerNorm stays in fp32 for numerical stability.
                for _m in worker.synthesizer.tts_model.modules():
                    if isinstance(_m, torch.nn.LayerNorm):
                        _m.float()
            elif precision == "bf16":
                worker.synthesizer.tts_model = worker.synthesizer.tts_model.to(
                    dtype=torch.bfloat16
                )
                # HiFiGAN vocoder uses cuFFT which does not support bf16.
                worker.synthesizer.tts_model.hifigan_decoder = (
                    worker.synthesizer.tts_model.hifigan_decoder.float()
                )
            print_err(f"COQUI BACKEND: {precision} applied.", flush=True)

        self._worker = worker
        self._device = device
        self._precision = precision
        self._loaded = True
        print_err("COQUI BACKEND: ready.", flush=True)

    def infer(
        self,
        text: str,
        voice_wav_path: str | None,
        language: str,
        speed: float = 1.0,
        params: dict | None = None,
    ) -> bytes:
        """Synthesize `text` to a complete WAV file and return its bytes."""
        import torch

        if not self._loaded or self._worker is None:
            raise RuntimeError(
                "Coqui backend: infer() called before load() succeeded."
            )
        if not text or not text.strip():
            raise ValueError("Coqui backend: input text is empty.")
        if language not in XTTS_V2_LANGUAGES:
            raise ValueError(
                f"Coqui backend: language '{language}' not supported. "
                f"Supported: {XTTS_V2_LANGUAGES}"
            )

        p = params or {}
        autocast_on = self._precision != "fp32" and self._device.startswith("cuda")
        autocast_dtype = torch.bfloat16 if self._precision == "bf16" else torch.float16

        # Coqui's tts_to_file writes to disk — use a temp file and read back.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            output_path = tmp.name
        try:
            with torch.autocast("cuda", dtype=autocast_dtype, enabled=autocast_on):
                self._worker.tts_to_file(
                    text=text,
                    speaker_wav=voice_wav_path,
                    language=language,
                    file_path=output_path,
                    speed=speed,
                    temperature=p.get("temperature", 0.75),
                    length_penalty=p.get("length_penalty", 1.0),
                    repetition_penalty=p.get("repetition_penalty", 5.0),
                    top_k=p.get("top_k", 50),
                    top_p=p.get("top_p", 0.85),
                )
            with open(output_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    def infer_stream(
        self,
        text: str,
        voice_wav_path: str | None,
        language: str,
        speed: float = 1.0,
        params: dict | None = None,
    ) -> Iterator[bytes]:
        """Stream XTTS-v2 synthesis as WAV chunks.

        Yields a RIFF/WAVE header first, then raw int16 PCM samples as
        they are produced by the model (~20 token chunks by default).
        """
        import torch

        if not self._loaded or self._worker is None:
            raise RuntimeError(
                "Coqui backend: infer_stream() called before load() succeeded."
            )
        if not text or not text.strip():
            raise ValueError("Coqui backend: input text is empty.")
        if language not in XTTS_V2_LANGUAGES:
            raise ValueError(
                f"Coqui backend: language '{language}' not supported."
            )

        p = params or {}
        model = self._worker.synthesizer.tts_model

        gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
            audio_path=[voice_wav_path]
        )

        yield _make_streaming_wav_header()

        for chunk in model.inference_stream(
            text, language, gpt_cond_latent, speaker_embedding,
            speed=speed,
            temperature=p.get("temperature", 0.75),
            length_penalty=p.get("length_penalty", 1.0),
            repetition_penalty=p.get("repetition_penalty", 5.0),
            top_k=p.get("top_k", 50),
            top_p=p.get("top_p", 0.85),
            stream_chunk_size=20,
        ):
            yield (chunk.squeeze() * 32767).to(torch.int16).cpu().numpy().tobytes()

    def unload(self) -> None:
        """Release the model and free VRAM. Idempotent."""
        if not self._loaded:
            return
        try:
            del self._worker
        except Exception:
            pass
        self._worker = None
        self._loaded = False
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def supported_languages(self) -> list[str]:
        """Return the list of XTTS-v2 language codes."""
        return list(XTTS_V2_LANGUAGES)
