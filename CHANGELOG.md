# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.3] - 2026-02-28

### Added
- Complete No-Sudo installation workflow.
- Pre-requisites section in `README.md` for `espeak-ng`, `curl`, and `file`.
- Automated local directory structure within the project folder for `models`, `voices`, and `cache`.

### Changed
- Refactored `setup_assets.sh` to remove `sudo apt` calls and redirect all storage to the local `assets/` directory.
- Updated `main_tts.py` default storage paths to align with the local project structure.

## [1.0.2] - 2026-02-28

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
