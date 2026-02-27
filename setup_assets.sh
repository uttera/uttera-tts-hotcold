#!/bin/bash
# Uttera TTS Asset Provisioning Script
# Version: 1.1.2
# Description: Automates the setup of system dependencies and all recommended Coqui models.

set -e

echo "🦾 Uttera - Provisioning Full Infrastructure Assets..."

# 1. Resolve TTS Binary Path
# We attempt to find the tts binary in the local venv or system path
if [ -f "./venv/bin/tts" ]; then
    TTS_BIN="./venv/bin/tts"
elif command -v tts &> /dev/null; then
    TTS_BIN=$(command -v tts)
else
    echo "[!] ERROR: 'tts' binary not found. Please run setup.sh first or ensure you are in the correct directory."
    exit 1
fi

echo "[*] Using TTS binary at: $TTS_BIN"

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

# 4. Environment Variables
export TTS_HOME="/opt/ai/models/speech/coqui-tts"

# 5. Model Provisioning (Initialization)
echo "[*] Provisioning Full Coqui Model Gallery (this may take several minutes)..."

echo "    -> [1/5] XTTS v2 (Orchestrator - Multilingual)..."
$TTS_BIN --model_name tts_models/multilingual/multi-dataset/xtts_v2 --list_language_idxs

echo "    -> [2/5] VITS LJSpeech (English Fast - Single Speaker)..."
$TTS_BIN --model_name tts_models/en/ljspeech/vits \
    --text "init" --out_path "/tmp/init_vits_en.wav"

echo "    -> [3/5] VITS VCTK (English Multi-speaker)..."
$TTS_BIN --model_name tts_models/en/vctk/vits --list_speaker_idxs

echo "    -> [4/5] VITS CSS10 (Spanish Native - Single Speaker)..."
$TTS_BIN --model_name tts_models/es/css10/vits \
    --text "Sistema Iniciado" --out_path "/tmp/init_vits_es.wav"

echo "    -> [5/5] YourTTS (Legacy Multilingual)..."
$TTS_BIN --model_name tts_models/multilingual/multi-dataset/your_tts --list_language_idxs

echo "✅ Full Infrastructure Provisioning Complete (5/5 Models)."
echo "⚠️  Reminder: Place your .wav reference files in /opt/ai/assets/voices/ to enable cloning."
