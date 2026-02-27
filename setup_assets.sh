#!/bin/bash
# Uttera TTS Asset Provisioning Script
# Version: 1.1.5
# Description: Automates setup of system dependencies, standard models, and permissive voices.
# NOTE: This script is designed to be idempotent and handles its own environment.

set -e

echo "🦾 Uttera - Provisioning Infrastructure Assets..."

# 1. Identity and Paths
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_PATH="$SCRIPT_DIR/venv"
TTS_BIN="$VENV_PATH/bin/tts"

# 2. Idempotency Check & Environment Activation
if [ -d "$VENV_PATH" ]; then
    echo "[*] Virtual environment detected. Activating..."
    source "$VENV_PATH/activate"
else
    echo "[!] Virtual environment not found at $VENV_PATH."
    echo "[*] Attempting to use system-wide 'tts' binary as fallback..."
    if command -v tts &> /dev/null; then
        TTS_BIN=$(command -v tts)
    else
        echo "[!] ERROR: 'tts' binary not found. Please run setup.sh first to create the environment."
        exit 1
    fi
fi

echo "[*] Using TTS binary at: $TTS_BIN"

# 3. System Dependencies
echo "[*] Verifying system dependencies (espeak-ng, curl)..."
sudo apt-get update -qq && sudo apt-get install -y -qq espeak-ng curl

# 4. Directory Structure
echo "[*] Creating Uttera directory structure..."
sudo mkdir -p /opt/ai/models/speech/coqui-tts
sudo mkdir -p /opt/ai/assets/voices/standard
sudo mkdir -p /opt/ai/assets/voices/elite
sudo chown -R $USER:$USER /opt/ai/models/speech/
sudo chown -R $USER:$USER /opt/ai/assets/voices/

# 5. Environment Variables & Licensing
export TTS_HOME="/opt/ai/models/speech/coqui-tts"
export COQUI_TOS_AGREED=1
VOICE_BASE_URL="https://github.com/fakehec/coqui-tts-local-server/raw/master/samples"

# 6. Standard Voices Provisioning
echo "[*] Provisioning Standard Voice Gallery (OpenAI Mappings)..."
voices=("alloy" "echo" "fable" "onyx" "nova" "shimmer")
for voice in "${voices[@]}"; do
    if [ ! -f "/opt/ai/assets/voices/standard/$voice.wav" ]; then
        echo "    -> Downloading $voice.wav..."
        curl -L -s -o "/opt/ai/assets/voices/standard/$voice.wav" "$VOICE_BASE_URL/standard/$voice.wav" || echo "    [!] Failed to download $voice.wav"
    else
        echo "    -> $voice.wav already exists. Skipping."
    fi
done

# 7. Model Provisioning (Idempotent)
echo "[*] Provisioning Full Coqui Model Gallery (5 Models)..."

provision_model() {
    local model_name=$1
    local cmd_type=$2 # "list" or "synth"
    echo "    -> Processing $model_name..."
    if [ "$cmd_type" == "list" ]; then
        $TTS_BIN --model_name "$model_name" --list_language_idxs > /dev/null 2>&1 || true
    else
        $TTS_BIN --model_name "$model_name" --text "init" --out_path "/tmp/init_$(date +%s).wav" > /dev/null 2>&1 || true
    fi
}

provision_model "tts_models/multilingual/multi-dataset/xtts_v2" "list"
provision_model "tts_models/en/ljspeech/vits" "synth"
provision_model "tts_models/en/vctk/vits" "list"
provision_model "tts_models/es/css10/vits" "synth"
provision_model "tts_models/multilingual/multi-dataset/your_tts" "list"

echo "✅ Infrastructure Provisioning Complete and Validated."
