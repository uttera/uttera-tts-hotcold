#!/bin/bash
# Uttera TTS Provisioning Script
# Version: 1.0.0
# Description: Automates the setup of system dependencies, Coqui models, and reference voices.

set -e

echo "🦾 Uttera - Initializing TTS Infrastructure Provisioning..."

# 1. System Dependencies
echo "[*] Installing system dependencies (espeak-ng)..."
sudo apt-get update && sudo apt-get install -y espeak-ng curl

# 2. Directory Structure
echo "[*] Creating Uttera directory structure..."
sudo mkdir -p /opt/ai/models/speech/coqui-tts
sudo mkdir -p /opt/ai/assets/voices/standard
sudo mkdir -p /opt/ai/assets/voices/elite
sudo chown -R $USER:$USER /opt/ai/models/speech/
sudo chown -R $USER:$USER /opt/ai/assets/voices/

# 3. Environment Variables
export TTS_HOME="/opt/ai/models/speech/coqui-tts"
VOICE_BASE_URL="https://github.com/fakehec/coqui-tts-local-server/raw/master/samples"

# 4. Standard Voices (OpenAI Compatibility)
echo "[*] Provisioning Standard Voice Gallery (OpenAI Mappings)..."
voices=("alloy" "echo" "fable" "onyx" "nova" "shimmer")
for voice in "${voices[@]}"; do
    echo "    -> Downloading $voice.wav..."
    curl -L -s -o "/opt/ai/assets/voices/standard/$voice.wav" "$VOICE_BASE_URL/standard/$voice.wav"
done

# 5. Elite Voices (Uttera Specialities)
echo "[*] Provisioning Elite Voice Gallery..."
elite_voices=("redacted-voice" "redacted-voice") # redacted-voice is mapped to 'assistant'
for voice in "${elite_voices[@]}"; do
    echo "    -> Downloading $voice.wav..."
    curl -L -s -o "/opt/ai/assets/voices/elite/$voice.wav" "$VOICE_BASE_URL/elite/$voice.wav"
done

# 6. Model Provisioning (Initialization)
# We use a temp reference file to initialize multi-speaker models
REF_VOICE="/opt/ai/assets/voices/standard/alloy.wav"

echo "[*] Provisioning Coqui Models (this may take several minutes)..."

echo "    -> [1/3] XTTS v2 (Orchestrator)..."
tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 \
    --text "System Online" --language_idx "en" \
    --speaker_wav "$REF_VOICE" --out_path "/tmp/init_xtts.wav" > /dev/null 2>&1

echo "    -> [2/3] VITS LJSpeech (English Fast)..."
tts --model_name tts_models/en/ljspeech/vits \
    --text "System Online" --out_path "/tmp/init_vits_en.wav" > /dev/null 2>&1

echo "    -> [3/3] VITS CSS10 (Spanish Natve)..."
tts --model_name tts_models/es/css10/vits \
    --text "Sistema Iniciado" --out_path "/tmp/init_vits_es.wav" > /dev/null 2>&1

echo "✅ Provisioning Complete. Your Uttera TTS node is ready."
