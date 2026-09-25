# CLONE_VOICES.md — Custom Voice Guide

This document describes how to equip the server with your own custom voices
alongside the OpenAI-compatible standard voices.

> **Use only audio you have the right to use.** Provide your own recordings, or
> samples you are licensed to use. Do **not** clone the voice of a real person
> without their explicit consent, and do not use copyrighted recordings
> (films, series, games, published performances) as reference material. No
> third-party audio is shipped with this software; you supply the samples.

## 🛡️ Technical sample requirements (the "raw material")

For the XTTS-v2 model to perform high-fidelity cloning, each reference file
should meet the following:

1. **Duration:** Between 6 and 12 seconds. Less than 6 s reduces tonal depth;
   more than 12 s increases initial loading latency without proportionally
   improving quality.
2. **Content:** A clear human voice — a complete sentence with natural
   intonation.
3. **Purity:** Zero background noise. No music, sound effects, or echo; external
   frequencies contaminate the output.
4. **Format:** `.wav` (PCM 16-bit or 32-bit float).
5. **Quality:** Minimum sample rate 22,050 Hz (44,100 Hz or higher recommended).
   Mono or stereo (the engine normalizes it internally).

## 🚀 Installation

Place your files in the assets directory defined by your environment variables
(default: `assets/voices/`), then reference them from `voices.json`.

### 📂 Directory structure

```text
assets/voices/
├── standard/        <-- OpenAI-compatibility voices
│   ├── alloy.wav
│   ├── echo.wav
│   ├── fable.wav
│   ├── onyx.wav
│   ├── nova.wav
│   └── shimmer.wav
└── elite/           <-- your own custom voices
    ├── my_voice.wav
    ├── narrator.wav
    └── assistant.wav
```

Map each file to a name in `voices.json`, e.g.:

```json
{
  "narrator": "elite/narrator.wav",
  "assistant": "elite/assistant.wav"
}
```

Then reload without restarting the engine:

```bash
curl -X POST http://localhost:9004/admin/reload-voices
```

## 🛠️ Preparing a sample from your own source

Start from audio you own or are licensed to use (your own recording is ideal).
The steps below extract a clean 6–12 s segment and master it for cloning.

### 1. Extract a clear segment

```bash
# Isolate a clean 10-second segment (adjust the start time)
ffmpeg -i my_recording.wav -ss 00:00:05 -t 10 -ac 1 -ar 22050 clear_sample.wav
```

### 2. Optional denoising (for older or noisy sources)

```bash
# 1. Isolate a short segment of pure background noise (no voice)
sox clear_sample.wav noise_only.wav trim 0 0.5
# 2. Generate the noise profile
sox noise_only.wav -n noiseprof voice_noise.prof
# 3. Apply noise reduction to the main sample
sox clear_sample.wav mastered_voice.wav noisered voice_noise.prof 0.21
```

### 3. One-step mastering (for a relatively clean source)

```bash
ffmpeg -i my_recording.wav \
  -ss 00:00:05 -t 10 \
  -acodec pcm_s16le -ar 44100 -ac 1 \
  -af "highpass=f=200, lowpass=f=3000, loudnorm=I=-16:TP=-1.5:LRA=11" \
  assets/voices/elite/my_voice.wav
```

### ⚙️ Command breakdown

* `-ss 00:00:05`: Start extraction at 5 seconds.
* `-t 10`: Extract exactly 10 seconds.
* `-acodec pcm_s16le`: Encode as 16-bit PCM (WAV standard).
* `-ar 44100 -ac 1`: 44.1 kHz sample rate, forced mono (cleaner for cloning).
* `-af "..."`: Audio filter chain:
    * `highpass=f=200`: Removes low-end rumble and mains hum.
    * `lowpass=f=3000`: Removes high-frequency hiss (raise to 5000 for modern,
      high-bitrate sources).
    * `loudnorm`: Normalizes to EBU R128 for consistent presence.

## 🔍 Tips

* **Normalization:** Normalize the sample volume to about -3 dB (Audacity,
  FFmpeg, etc.).
* **Cleaning:** Apply noise reduction if the source is from an analog source.
* **Fidelity:** Clone quality is proportional to sample quality. Poor raw
  material yields a flat result.
