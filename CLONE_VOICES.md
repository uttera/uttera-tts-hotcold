# CLONE_VOICES.md - Sonic Identity Manual (Custom Cloning)

This document details the procedure for equipping the server with the Elite Gallery voices and OpenAI standards. For intellectual property and copyright reasons, third-party audio files are not provided with this software.

## 🛡️ Technical Sample Requirements (The "Raw Material")

For the XTTSv2 model to perform high-fidelity cloning, each reference file must comply with the following acoustic intelligence parameters:

1. **Duration:** Between 6 and 12 seconds. Less than 6 seconds reduces tonal depth; more than 12 increases initial loading latency without proportionally improving quality.
2. **Content:** Clear human voice. It must contain a complete sentence with natural intonation variations.
3. **Purity:** ZERO background noise. No music, sound effects, explosions, or echo. The presence of external frequencies will contaminate the voice output.
4. **Format:** .wav (PCM 16-bit or 32-bit float).
5. **Quality:** Minimum sampling rate of 22,050 Hz (44,100 Hz or higher recommended). Mono or Stereo (the engine will normalize it internally).

## 🚀 Installation Procedure

For automatic mappings to work, files must be placed in the assets directory defined in your environment variables (default: `/opt/ai/assets/voices/`).

### 📂 Directory Structure:

```text
/opt/ai/assets/voices/
├── standard/        <-- OpenAI compatibility voices
│   ├── alloy.wav
│   ├── echo.wav
│   ├── fable.wav
│   ├── onyx.wav
│   ├── nova.wav
│   └── shimmer.wav
└── elite/           <-- Elite Gallery of Artificial Intelligences
    ├── redacted-voice.wav    (Mapped to "narrator")
    ├── redacted-voice.wav    (Mapped to "voice-b")
    ├── redacted-voice.wav         (Mapped to "voice-c")
    ├── redacted-voice.wav
    ├── redacted.wav
    ├── redacted.wav
    ├── redacted.wav
    ├── redacted.wav
    └── redacted.wav
```

## 🛠️ Advanced Workflow: From Source to Sample

To obtain a professional-grade sample from any online source (such as YouTube) or a local file, you can follow this end-to-end workflow. This process involves downloading, precise extraction, and acoustic optimization.

### 1. Download & Initial Extraction (YouTube)
If your source is on YouTube, use `yt-dlp` to extract the highest quality audio directly:

```bash
yt-dlp -x --audio-format wav --audio-quality 0 "https://www.youtube.com/watch?v=VIDEO_ID" -o "raw_source.wav"
```

### 2. Identify the Target Segment
Find a segment (6-12s) where the character speaks clearly without music or background noise. Note the start time (`-ss`) and duration (`-t`).

### 3. Professional Mastering with FFmpeg
Run the following optimized command to isolate and master the voice:

```bash
ffmpeg -i raw_source.wav \
  -ss 00:01:25 -t 10 \
  -acodec pcm_s16le -ar 44100 -ac 1 \
  -af "highpass=f=200, lowpass=f=3000, loudnorm=I=-16:TP=-1.5:LRA=11" \
  /opt/ai/assets/voices/elite/target_voice.wav
```

### ⚙️ Command Breakdown:
* `-ss 00:01:25`: Starts extraction at 1 minute and 25 seconds.
* `-t 10`: Extracts exactly 10 seconds.
* `-acodec pcm_s16le`: Encodes in 16-bit PCM (WAV standard).
* `-ar 44100 -ac 1`: Sets 44.1kHz sample rate and forces Mono (cleaner for cloning).
* `-af "..."`: Audio filters chain:
    * `highpass=f=200`: Removes low-end rumble and power line hum.
    * `lowpass=f=3000`: Removes high-frequency hiss (expand to 5000 for modern high-bitrate sources).
    * `loudnorm`: Normalizes the voice to EBU R128 standards for a punchy, consistent presence.

## 🔍 Tips for Sophisticated Cloning

* **Normalization:** Use tools like Audacity or FFmpeg to normalize the sample volume to -3dB.
* **Cleaning:** Apply a noise reduction filter if the original clip comes from an analog source or an old film (such as a character).
* **Fidelity:** The quality of the clone is directly proportional to the quality of the sample. If the "Raw Material" is poor, the server's response will lack soul.

"Perfection is not a detail, but details make perfection."
-- Uttera
