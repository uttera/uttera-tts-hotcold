# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.4] - 2026-02-28

### Added
- **Stable Production Release:** Golden version for the Uttera.
- Performance verified on Sphinx and local nodes (3 concurrent streams in ~18s).
- Full architectural symmetry between production and repository branches.

### Changed
- Refined `main_tts.py` header with official Copyright and Architecture summary.

## [1.1.3] - 2026-02-28

### Fixed
- Corrected CLI flags in Child Lane (`--no-progress_bar` and `--use_cuda`) for compatibility with local `tts` binary, resolving "unrecognized arguments" errors.

## [1.1.2] - 2026-02-28

### Fixed
- Resolved function name mismatch in `create_speech` router (`run_tts_child_lane` vs `run_tts_child_lane_async`).

## [1.1.1] - 2026-02-28

### Added
- Restored `DEBUG` mode verbosity by disabling subprocess output capture and forcing `flush=True` on all prints.
- Detailed error reporting for FFmpeg and Subprocess failures.

## [1.1.0] - 2026-02-28

### Added
- Full architectural restoration from production `v123` reference (Sphinx node).
- Implementation of `asyncio.create_subprocess_exec` with pipe consumption to bypass GIL and prevent buffer deadlocks.
- Support for Stark Elite voice gallery (a character, a voice, a character, etc.) and Spanish by default.
- Modernized `requirements.txt` and `setup.sh` with hotfixes for Python 3.14 stability.

## [1.0.6] - 2026-02-28

### Added
- Consolidated architecture headers and GNU GPL v3 license from reference implementation.
- Detailed description of the hybrid concurrency model (Hot/Cold workers).

## [1.0.3] - 2026-02-28

### Added
- Complete No-Sudo installation workflow.
- Local directory structure within the project folder for `assets/` (models, voices, cache).
- Prerequisites section in README for `espeak-ng`, `curl`, and `file`.

## [1.0.0] - 2026-02-27

### Added
- Initial stable production release.
- End-to-end voice cloning pipeline documentation.
- Support for character voice engineering and specialized synthesis.
