# Contributing to uttera-tts-hotcold

Thanks for your interest in contributing. This project is maintained as
part of the [Uttera](https://uttera.ai) voice stack under the Apache-2.0
license.

## Ground rules

- Be respectful. The [Code of Conduct](CODE_OF_CONDUCT.md) applies to all
  interactions in this repository.
- Keep changes focused. One pull request per feature or fix is ideal.
- Open an issue before starting large changes so we can agree on direction
  before you invest time.

## Reporting bugs

Before opening a bug report:

1. Search [existing issues](../../issues) to see if someone has already
   reported the same problem.
2. If not, open a new issue using the "Bug report" template. Include:
   - Exact server version (`curl /health | jq .server_version`)
   - Python version, GPU model, driver version
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant logs (redact any sensitive data first)

## Requesting features

Use the "Feature request" template. Describe the use case before the
proposed solution — it helps reviewers understand the underlying need and
suggest alternatives.

## Pull requests

1. Fork the repo and create a feature branch from `master`:
   ```bash
   git checkout -b feat/my-feature
   ```
2. Make your changes in small, logical commits. Commit messages should
   follow the existing style (see `git log --oneline`).
3. Run any relevant tests locally before pushing.
4. Open a PR against `master`. Fill in the PR template.
5. The CODEOWNERS file requires review by the maintainer before merge.
6. Address review feedback by pushing additional commits to the same
   branch (we squash on merge, so don't worry about tidy history).

## Commit message conventions

Following the existing project conventions:

```
<type>: <short description> (optional version tag)

<optional longer description>
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`.

Example: `feat: add VoxCPM2 backend support (v2.0.0)`

## Coding style

- Python: follow PEP 8 (enforced via `ruff` in CI once it's wired up).
- Line length: 100 characters max.
- No trailing whitespace, single final newline.
- Type hints are appreciated but not required everywhere.

## Adding a new TTS backend

If you want to contribute a new TTS engine adapter:

1. Read [docs/backends.md](docs/backends.md) for the full plugin contract.
2. Create `backends/<name>_backend.py` inheriting from `TTSBackend`.
3. Create `requirements-<name>.txt` with backend-specific dependencies.
4. Add a smoke test for the new backend in `.github/workflows/ci.yml`.
5. Open a PR with a description of the engine, its license, and a sample
   synthesis output.

## Developer Certificate of Origin (DCO)

By contributing to this project, you certify that you wrote the code or
have the right to submit it under the project's license (Apache-2.0).
Your commit must include a `Signed-off-by` line — most editors can add
this automatically with `git commit -s`.

## License

By submitting a contribution, you agree to license your work under the
terms of the [Apache License 2.0](LICENSE).

---

For questions about contributing, email **maintainers@uttera.ai** or open
a discussion.
