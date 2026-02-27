#!/bin/bash
# Uttera TTS Asset Provisioning Script
# Version: 1.1.1
# Description: Automates the setup of system dependencies and all recommended Coqui models.
# Note: Reference voices must be provided manually by the user in /opt/ai/assets/voices/

set -e

echo "🦾 Uttera - Provisioning Full Infrastructure Assets..."

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

# 4. Model Provisioning (Initialization)
echo "[*] Provisioning Full Coqui Model Gallery (this may take several minutes)..."

# Note: For multi-speaker/cloning models, we check for a reference file.
# If not present, we skip the initialization step but the model stays downloaded.

echo "    -> [1/5] XTTS v2 (Orchestrator - Multilingual)..."
# We don't init without wav, but the command triggers download
tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 --list_language_idxs > /dev/null 2>&1 || true

echo "    -> [2/5] VITS LJSpeech (English Fast - Single Speaker)..."
tts --model_name tts_models/en/ljspeech/vits \
    --text "init" --out_path "/tmp/init_vits_en.wav" > /dev/null 2>&1

echo "    -> [3/5] VITS VCTK (English Multi-speaker)..."
tts --model_name tts_models/en/vctk/vits --list_speaker_idxs > /dev/null 2>&1 || true

echo "    -> [4/5] VITS CSS10 (Spanish Native - Single Speaker)..."
tts --model_name tts_models/es/css10/vits \
    --text "Sistema Iniciado" --out_path "/tmp/init_vits_es.wav" > /dev/null 2>&1

echo "    -> [5/5] YourTTS (Legacy Multilingual)..."
tts --model_name tts_models/multilingual/multi-dataset/your_tts --list_language_idxs > /dev/null 2>&1 || true

echo "✅ Full Infrastructure Provisioning Complete (5/5 Models)."
echo "⚠️  Reminder: Place your .wav reference files in /opt/ai/assets/voices/ to enable cloning."
