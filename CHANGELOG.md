# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.8] - 2026-02-27

### Added
- Standard voices (Alloy, Echo, Fable, Onyx, Nova, Shimmer) now automatically provisioned via `setup_assets.sh`.
- Consolidated "Security & Network Note" in README.
- Automatic non-commercial license agreement bypass in provisioning scripts.

### Fixed
- Idempotency in `setup_assets.sh` (skips existing assets).
- Path discovery for virtual environments in provisioning scripts.
- Default vocal backup: system now reliably falls back to 'alloy'.

## [1.3.7] - 2026-02-27

### Changed
- Reverted server execution to direct **Uvicorn** (`uvicorn main_tts:app`).
- Default network binding set to `127.0.0.1` for enhanced security.
- Version bump for architectural synchronization.

## [1.3.0] - 2026-02-27

### Added
- Unified `setup.sh` orchestrator.
- Modular `setup_assets.sh` for infrastructure provisioning.

## [1.2.9] - 2026-02-27

### Fixed
- Model download syntax for multi-speaker and VITS architectures.
- Requirement of `espeak-ng` system dependency.

## [1.2.4] - 2026-02-27

### Added
- Dynamic language switching via `language` parameter.
- Language-aware MD5 caching.

## [1.2.3] - 2026-02-27

### Added
- Initial release: Hybrid Hot/Cold lane architecture.
- OpenAI TTS API compliance.
- Elite voice gallery mappings.
