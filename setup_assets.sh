#!/bin/bash
# Uttera TTS Asset Provisioning Script
# Version: 1.1.0
# Description: Automates the setup of system dependencies and Coqui models.
# Note: Reference voices must be provided manually by the user in /opt/ai/assets/voices/

set -e

echo "🦾 Uttera - Provisioning Infrastructure Assets..."

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
# Use a system-wide dummy wav if no reference is present, or skip XTTS init
echo "[*] Provisioning Coqui Models (this may take several minutes)..."

echo "    -> [1/2] VITS LJSpeech (English Fast)..."
tts --model_name tts_models/en/ljspeech/vits \
    --text "init" --out_path "/tmp/init_vits_en.wav" > /dev/null 2>&1

echo "    -> [2/2] VITS CSS10 (Spanish Native)..."
tts --model_name tts_models/es/css10/vits \
    --text "init" --out_path "/tmp/init_vits_es.wav" > /dev/null 2>&1

echo "⚠️  XTTS v2 model requires manual initialization with a reference .wav file."
echo "✅ Infrastructure Provisioning Complete."
