# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.5] - 2026-02-28

### Added
- Restored full Debian/Ubuntu style header in `main_tts.py` including license and architecture description.
- Explicit GNU GPL v3 license declaration.

## [1.0.4] - 2026-02-28

### Added
- Automated Hotfix in `setup.sh` to resolve `isin_mps_friendly` import error in Coqui-TTS/Transformers.
- Support for `torchcodec` via `coqui-tts[codec]` extra (required for Pytorch 2.9+).

### Changed
- Modernized `requirements.txt` to prevent massive backtracking and version conflicts.
- Updated minimum version of `transformers` and `pydantic` for better environment stability.

## [1.0.0] - 2026-02-27

### Added
- Initial stable production release.
- End-to-end voice cloning pipeline documentation.
- Integrated SoX denoising workflow for high-fidelity audio samples.
- Support for automated sample rate conversion.
- Support for character voice engineering and specialized synthesis.

### Changed
- Improved PyPI compatibility by renaming package dependencies.
- Updated documentation for local-only private inference.

### Fixed
- Various minor bugs in the FastAPI/Uvicorn interface.
