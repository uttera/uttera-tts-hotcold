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

## 🛠️ Advanced Workflow: Extracting Samples with FFmpeg

To obtain a professional-grade sample from a source file (such as a movie or interview), you can use the following optimized FFmpeg workflow. This process isolates the voice, removes extreme frequencies, and normalizes the volume.

### 1. Identify the Target Segment
Find a segment where the character speaks clearly without music or background noise. Note the start time (`-ss`) and duration (`-t`).

### 2. High-Fidelity Extraction Command
Run the following command to extract and pre-process the audio:

```bash
ffmpeg -i input_movie.mkv \
  -ss 01:22:15 -t 10 \
  -vn -acodec pcm_s16le -ar 44100 -ac 1 \
  -af "highpass=f=200, lowpass=f=3000, loudnorm=I=-16:TP=-1.5:LRA=11" \
  /opt/ai/assets/voices/elite/target_voice.wav
```

### ⚙️ Command Breakdown:
* `-ss 01:22:15`: Starts extraction at 1 hour, 22 minutes, and 15 seconds.
* `-t 10`: Extracts exactly 10 seconds.
* `-vn`: Discards video stream.
* `-acodec pcm_s16le`: Encodes in 16-bit PCM (WAV standard).
* `-ar 44100 -ac 1`: Sets 44.1kHz sample rate and forces Mono (cleaner for cloning).
* `-af "..."`: Audio filters chain:
    * `highpass=f=200`: Removes low-end rumble and hum.
    * `lowpass=f=3000`: Removes high-frequency hiss (adjust to 4000-5000 for modern voices).
    * `loudnorm`: Normalizes the voice to EBU R128 standards for consistent volume.

## 🔍 Tips for Sophisticated Cloning

* **Normalization:** Use tools like Audacity or FFmpeg to normalize the sample volume to -3dB.
* **Cleaning:** Apply a noise reduction filter if the original clip comes from an analog source or an old film (such as a character).
* **Fidelity:** The quality of the clone is directly proportional to the quality of the sample. If the "Raw Material" is poor, the server's response will lack soul.

"Perfection is not a detail, but details make perfection."
-- Uttera
