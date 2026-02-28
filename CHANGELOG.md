# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-02-28

### Added
- Local `assets/` directory within the project folder for standardizing temporary and processed file storage.
- Documentation for `video` and `render` system groups to enable GPU acceleration without `sudo`.
- Network permission guidelines for binding to port `5100`.

### Changed
- Refactored `main_tts.py` to eliminate all `sudo` requirements, ensuring user-friendly operation.
- Updated `README.md` to be fully in English, including installation and hardware acceleration steps.
- Updated `setup.sh` with a dynamic path resolver for the `transformers` compatibility patch.

## [1.0.1] - 2026-02-28

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
