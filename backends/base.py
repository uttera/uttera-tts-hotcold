#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Hugo L. Espuny
#
# Part of the Uttera voice stack (https://uttera.ai).
# See LICENSE and NOTICE at the repository root.
"""
backends/base.py — Abstract base class for TTS backends.

A TTS backend adapts a specific TTS engine (Coqui XTTS-v2, VoxCPM2, Kokoro,
StyleTTS2, ...) to a uniform interface that the server can drive regardless
of which engine is loaded.

The server code in `main_tts.py` and `cold_worker_tts.py` only interacts
with the `TTSBackend` abstract methods. Swapping engines is a matter of
setting the `TTS_BACKEND` environment variable — no server code changes.

## Contract summary

Each backend must be:

- **Instantiable with zero arguments** (configuration read from env vars
  inside `load()`).
- **Thread-unsafe by default** — a single backend instance is owned by a
  single process (the hot worker or one cold worker). The server is
  responsible for serialising access; backends do not need to implement
  internal locking.
- **Re-entrant on repeated `load()` calls only by explicit contract** —
  by default a backend loads the model once per process. If re-loading is
  needed, destroy the instance and create a new one.

## Lifecycle

    backend = load_backend()          # factory picks from TTS_BACKEND env
    backend.load(device="cuda", precision="fp16")
    wav_bytes = backend.infer(text="hi", voice_wav_path="...", ...)
    for chunk in backend.infer_stream(...):  # optional
        ...
    backend.unload()
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class TTSBackend(ABC):
    """Abstract TTS backend.

    Subclasses must override every abstract method and set the two class
    attributes:

    - `name` — a short, lowercase, machine-friendly identifier.
    - `supports_streaming` — True if the backend implements
      `infer_stream()`; False otherwise. The server will reject stream
      requests with HTTP 501 when this is False.
    """

    #: Short, lowercase machine-friendly identifier (e.g. "coqui", "voxcpm").
    name: str = ""

    #: Whether this backend implements `infer_stream()`. If False, the
    #: server returns HTTP 501 for `POST /v1/audio/speech/stream`.
    supports_streaming: bool = False

    @abstractmethod
    def load(self, device: str = "cuda", precision: str = "fp32") -> None:
        """Load the model into memory (typically VRAM).

        Called once per process shortly after instantiation. May take tens
        of seconds (model download, weight loading, CUDA graph warmup).
        Raises on failure — the caller treats any exception as fatal for
        this worker.

        Parameters
        ----------
        device : str
            Target device. Accepted values: "cuda", "cuda:N", "cpu".
        precision : str
            Weight precision. Accepted values: "fp32", "fp16", "bf16".
            Not every backend implements every precision; a backend MAY
            fall back to a sensible default and log a warning rather than
            raising.
        """
        raise NotImplementedError

    @abstractmethod
    def infer(
        self,
        text: str,
        voice_wav_path: str | None,
        language: str,
        speed: float = 1.0,
        params: dict | None = None,
    ) -> bytes:
        """Run synchronous TTS inference and return a complete WAV payload.

        Parameters
        ----------
        text : str
            Text to synthesize. Must be non-empty.
        voice_wav_path : str or None
            Absolute path to a reference audio file for voice cloning /
            conditioning. If None, the backend uses its default voice.
        language : str
            ISO language code ("en", "es", "fr", ...). If the backend does
            not support the requested language it MUST raise a `ValueError`.
        speed : float
            Speed multiplier around 1.0. Backends that do not support
            speed adjustment SHOULD ignore the parameter silently.
        params : dict or None
            Backend-specific tuning parameters (temperature, top_k, etc.).
            Unknown keys MUST be ignored (forward-compatibility).

        Returns
        -------
        bytes
            Complete WAV file contents (RIFF header + PCM data).
        """
        raise NotImplementedError

    def infer_stream(
        self,
        text: str,
        voice_wav_path: str | None,
        language: str,
        speed: float = 1.0,
        params: dict | None = None,
    ) -> Iterator[bytes]:
        """Run streaming TTS inference, yielding WAV chunks in order.

        Only called if `self.supports_streaming` is True. Default
        implementation raises `NotImplementedError` so backends without
        streaming do not need to override it.

        Each yielded chunk is a complete, playable WAV fragment (with its
        own RIFF header if the backend uses headered chunks, otherwise raw
        PCM — documented per backend).

        Parameters match `infer()` exactly.
        """
        raise NotImplementedError(
            f"Backend '{self.name}' does not support streaming."
        )

    @abstractmethod
    def unload(self) -> None:
        """Free VRAM / release model resources.

        Called when the worker is retiring (graceful shutdown, idle
        timeout of a cold worker, etc.). After `unload()` the instance
        MUST NOT be used again for inference; the caller creates a fresh
        instance when needed.

        MUST be idempotent — calling it twice is a no-op on the second
        call, not an error.
        """
        raise NotImplementedError

    @abstractmethod
    def supported_languages(self) -> list[str]:
        """Return the list of ISO language codes this backend can handle.

        Used to populate the `GET /v1/voices` endpoint and to validate
        incoming requests early. MUST be callable before or after
        `load()` — i.e. it should read a static list (e.g. hardcoded or
        from a config file), not probe the loaded model.
        """
        raise NotImplementedError
