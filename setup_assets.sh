#!/bin/bash
# Uttera TTS Asset Provisioning Script
# Version: 1.1.4
# Description: Automates setup of system dependencies, standard models, and permissive voices.
# Note: Elite voices (assistant/voice-c) are NOT included and must be provisioned via CLONE_VOICES.md

set -e

echo "🦾 Uttera - Provisioning Infrastructure Assets..."

# 1. Resolve TTS Binary Path
if [ -f "./venv/bin/tts" ]; then
    TTS_BIN="./venv/bin/tts"
elif command -v tts &> /dev/null; then
    TTS_BIN=$(command -v tts)
else
    echo "[!] ERROR: 'tts' binary not found. Please run setup.sh first."
    exit 1
fi

# 2. System Dependencies
echo "[*] Installing system dependencies (espeak-ng)..."
sudo apt-get update && sudo apt-get install -y espeak-ng curl

# 3. Directory Structure
echo "[*] Creating Uttera directory structure..."
sudo mkdir -p /opt/ai/models/speech/coqui-tts
sudo mkdir -p /opt/ai/assets/voices/standard
sudo mkdir -p /opt/ai/assets/voices/elite
sudo chown -R $USER:$USER /opt/ai/models/speech/
sudo chown -R $USER:$USER /opt/ai/assets/voices/

# 4. Environment Variables & Licensing
export TTS_HOME="/opt/ai/models/speech/coqui-tts"
export COQUI_TOS_AGREED=1
VOICE_BASE_URL="https://github.com/fakehec/coqui-tts-local-server/raw/master/samples"

# 5. Standard Voices Provisioning (Permissive Samples)
echo "[*] Provisioning Standard Voice Gallery (OpenAI Mappings)..."
voices=("alloy" "echo" "fable" "onyx" "nova" "shimmer")
for voice in "${voices[@]}"; do
    echo "    -> Downloading $voice.wav..."
    curl -L -s -o "/opt/ai/assets/voices/standard/$voice.wav" "$VOICE_BASE_URL/standard/$voice.wav" || echo "    [!] Failed to download $voice.wav"
done

# 6. Model Provisioning
echo "[*] Provisioning Full Coqui Model Gallery (5 Models)..."

echo "    -> [1/5] XTTS v2 (Orchestrator)..."
$TTS_BIN --model_name tts_models/multilingual/multi-dataset/xtts_v2 --list_language_idxs > /dev/null

echo "    -> [2/5] VITS LJSpeech (English Fast)..."
$TTS_BIN --model_name tts_models/en/ljspeech/vits --text "init" --out_path "/tmp/init_vits_en.wav" > /dev/null

echo "    -> [3/5] VITS VCTK (English Multi-speaker)..."
$TTS_BIN --model_name tts_models/en/vctk/vits --list_speaker_idxs > /dev/null

echo "    -> [4/5] VITS CSS10 (Spanish Native)..."
$TTS_BIN --model_name tts_models/es/css10/vits --text "Sistema Iniciado" --out_path "/tmp/init_vits_es.wav" > /dev/null

echo "    -> [5/5] YourTTS (Legacy Multilingual)..."
$TTS_BIN --model_name tts_models/multilingual/multi-dataset/your_tts --list_language_idxs > /dev/null

echo "✅ Infrastructure Provisioning Complete."
echo "⚠️  Reminder: Provision Elite voices manually as per CLONE_VOICES.md."
