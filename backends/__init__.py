#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Hugo L. Espuny
#
# Part of the Uttera voice stack (https://uttera.ai).
# See LICENSE and NOTICE at the repository root.
"""
backends/__init__.py — Backend factory.

Usage in server code:

    from backends import load_backend
    backend = load_backend()
    backend.load(device="cuda", precision="fp16")

The environment variable `TTS_BACKEND` selects the implementation.
Default: "coqui". The factory imports `backends.<name>_backend` and
returns an instance of its `Backend` class.

Adding a new backend:

1. Create `backends/<name>_backend.py` with a `Backend` class that
   inherits from `TTSBackend` and implements all abstract methods.
2. Add any backend-specific dependencies to `requirements-<name>.txt`.
3. Document the backend in `docs/backends.md`.

Optional: add a lightweight smoke test under `.github/workflows/ci.yml`.
"""
from __future__ import annotations

import importlib
import os

from backends.base import TTSBackend


DEFAULT_BACKEND = "coqui"


def load_backend(name: str | None = None) -> TTSBackend:
    """Instantiate the backend selected by `TTS_BACKEND` (or `name` arg).

    Parameters
    ----------
    name : str, optional
        Override the backend name. If None, reads `TTS_BACKEND` env var;
        if that is also unset, falls back to `DEFAULT_BACKEND`.

    Returns
    -------
    TTSBackend
        A freshly-instantiated backend. The caller is responsible for
        calling `.load()` before inference.

    Raises
    ------
    ModuleNotFoundError
        If the backend module cannot be imported. The error message
        includes the attempted module path so the user can verify
        installation of backend-specific dependencies.
    AttributeError
        If the backend module does not export a `Backend` class.
    """
    if name is None:
        name = os.environ.get("TTS_BACKEND", DEFAULT_BACKEND).strip().lower()

    if not name:
        name = DEFAULT_BACKEND

    module_path = f"backends.{name}_backend"
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            f"TTS backend '{name}' not found (tried importing {module_path}). "
            f"Check TTS_BACKEND env var and backend-specific dependencies "
            f"(see requirements-{name}.txt)."
        ) from e

    try:
        backend_cls = module.Backend
    except AttributeError as e:
        raise AttributeError(
            f"Backend module '{module_path}' must export a class named "
            f"'Backend' that inherits from backends.base.TTSBackend."
        ) from e

    instance = backend_cls()
    if not isinstance(instance, TTSBackend):
        raise TypeError(
            f"Backend class in '{module_path}' must inherit from "
            f"backends.base.TTSBackend (got {type(instance).__name__})."
        )
    return instance


__all__ = ["TTSBackend", "load_backend", "DEFAULT_BACKEND"]
