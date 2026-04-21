# Project history

## Origins

This software originated as a personal project by **Hugo L. Espuny**.
The author was a Debian developer (`hec@debian.org`) until 2004. Among his
contributions to the Debian project were the **first official Debian
packages of PHP-Nuke and Drupal** — two content management systems that
would go on to shape the early web.

## The industrial years

After stepping away from Debian in 2004, the author moved into the private
industrial sector, building and running businesses that had little to do
with writing code professionally. Software remained a personal passion
during that period — a craft practiced in spare hours, far from the
spotlight of open source contribution.

## The AI turn — November 2025

In November 2025, the author began experimenting with local AI installations
— Ollama, Open WebUI, and the first wave of self-hosted inference stacks.
The goal was personal and deliberate: build a complete AI interface that
could run entirely under local sovereignty, with no dependency on cloud
vendors.

Along the way, a practical gap became clear: to make that vision real, he
needed **voice**. Specifically, he needed Text-to-Speech and Speech-to-Text
servers that could serve multiple front-end clients **concurrently**, the
way a real backend does.

High-quality low-level models already existed — OpenAI's Whisper for STT,
Coqui's XTTS-v2 for TTS. But neither scaled gracefully to server-side
concurrency on consumer-class GPUs. They were designed for one-shot local
invocation, not for being hit by a busy frontend.

The first server written was in fact the Whisper one: a **Transformer-based
speech-to-text engine** wrapped in a hot/cold pool. The TTS companion came
a few weeks later, once the concurrency pattern proved itself. The name
**Uttera** reflects both heritages. From the English verb "to utter" (to
speak aloud, to pronounce, to give audible expression to). Formally, the
name is a backronym of **U**niversal **T**ext **T**ransformer **E**ngine
for **R**ealtime **A**udio. The project was a STT/TTS server before the
name existed; the name caught up to the product.

## The hot/cold architecture is born

The original design goal was specific and constrained:

- Lightweight servers
- GPU-accelerated
- Small VRAM footprint
- Able to run on consumer GPUs without saturating all resources
- Able to scale dynamically when concurrent load arrived

From those constraints emerged the **hot/cold worker pool**: a hot worker
keeps the model resident in VRAM for instant response; cold workers are
spawned on demand as subprocesses when the hot lane is busy and VRAM is
available, then retired when idle. The design was deliberately simple:
no orchestrator, no Kubernetes, no complex scheduler — just Python,
subprocesses, and honest accounting.

It worked. It still does. These two repositories are the result.

## Enter OpenClaw — December 2025

In December 2025, **OpenClaw** happened. What had begun as two marginal
servers scratching one developer's personal itch suddenly had a potential
audience of thousands: self-hosters, home-lab users, AI researchers, and
anyone else who wanted a local voice layer without a cloud middleman.

At that moment the author decided to **publish these servers as open
source**, as a contribution to the broader AI revolution — not as a
product, but as infrastructure for people who value local sovereignty
over their AI stack.

## Current status — April 2026

The repositories have completed their migration to the
[Uttera](https://github.com/uttera) organization and are part of the
broader [Uttera voice stack](https://uttera.ai). Four production
servers ship today under that umbrella:

- **`uttera-tts-hotcold`** (*this repository*) — hot/cold pool with
  pluggable backends (Coqui XTTS-v2, VoxCPM2). Ideal for consumer
  GPUs and home-lab deployments. The plugin architecture landed with
  v2.0.0 (April 2026).
- **`uttera-tts-vllm`** — high-throughput single-process server on
  top of `nano-vllm-voxcpm`'s continuous batcher. VoxCPM2-only by
  design; the single-backend focus is what buys the concurrency it
  delivers. Ideal for cloud, multi-tenant, large-VRAM GPUs.
- **`uttera-stt-hotcold`** — STT sibling of this repository (OpenAI
  Whisper + optional LibreTranslate pipeline).
- **`uttera-stt-vllm`** — STT sibling of `uttera-tts-vllm`
  (Whisper-v3-turbo via vLLM's native speech path).

All four share a common health-check schema, Redis self-registration
protocol, cache opt-out semantics, and sit behind the same
[echo-gatekeeper](https://github.com/uttera) for tier gating, rate
limits, and billing.

The original design philosophy, set during the first hot/cold
experiments, remains unchanged:

- Respect the user's hardware
- Respect the user's privacy
- Respect the user's freedom to run the stack anywhere, under any
  commercially-compatible license
- Keep the code simple enough to read in an afternoon

Everything else is negotiable.

---

## Acknowledgments

- The **Debian Project**, where the author learned what open source
  engineering looks like at its best.
- The **Coqui team**, for XTTS-v2 and the Coqui TTS library.
- **OpenAI**, for releasing Whisper under a truly permissive license.
- The **SYSTRAN** team behind faster-whisper.
- The **OpenClaw** community, for turning a personal project into
  something worth sharing.
- **Google Gemini** and **Anthropic Claude**, AI assistants that
  contributed substantively to the code, architecture, and documentation
  under the author's direction. See [AUTHORS.md](AUTHORS.md) for details.

---

## Contact

For any question, bug, or conversation about the project, please open
an Issue or Discussion in any of the
[Uttera](https://github.com/uttera) repositories on GitHub. Personal
email is intentionally omitted — GitHub is the canonical place where
the work happens and where contributions are welcome.

---

*Part of the [Uttera](https://uttera.ai) voice stack.*
