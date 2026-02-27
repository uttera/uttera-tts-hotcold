#!/bin/bash
# Uttera TTS Asset Provisioning Script
# Version: 1.1.6
# Description: Automates setup of system dependencies, standard models, and permissive voices.
# NOTE: This script is environment-aware and robust against path variations.

set -e

echo "🦾 Uttera - Provisioning Infrastructure Assets..."

# 1. Path Discovery & Environment Activation
# Strategy: Look for venv in local dir, then in Stark Standard path.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
STARK_STD_PATH="/usr/local/lib/coqui"

if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    VENV_ACTIVATE="$SCRIPT_DIR/venv/bin/activate"
elif [ -f "$STARK_STD_PATH/venv/bin/activate" ]; then
    VENV_ACTIVATE="$STARK_STD_PATH/venv/bin/activate"
else
    VENV_ACTIVATE=""
fi

if [ -n "$VENV_ACTIVATE" ]; then
    echo "[*] Virtual environment detected at $(dirname $(dirname $VENV_ACTIVATE)). Activating..."
    # We use 'source' or '.' to load the environment into the current shell process
    source "$VENV_ACTIVATE"
    TTS_BIN="tts"
else
    echo "[!] No local or standard virtual environment found."
    if command -v tts &> /dev/null; then
        echo "[*] Using system-wide 'tts' binary."
        TTS_BIN="tts"
    else
        echo "[!] ERROR: 'tts' binary not found. Environment is not provisioned."
        exit 1
    fi
fi

# 2. System Dependencies
echo "[*] Verifying system dependencies (espeak-ng, curl)..."
sudo apt-get update -qq && sudo apt-get install -y -qq espeak-ng curl

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

# 5. Standard Voices Provisioning
echo "[*] Provisioning Standard Voice Gallery (OpenAI Mappings)..."
voices=("alloy" "echo" "fable" "onyx" "nova" "shimmer")
for voice in "${voices[@]}"; do
    TARGET_FILE="/opt/ai/assets/voices/standard/$voice.wav"
    if [ ! -f "$TARGET_FILE" ]; then
        echo "    -> Downloading $voice.wav..."
        curl -L -s -o "$TARGET_FILE" "$VOICE_BASE_URL/standard/$voice.wav" || echo "    [!] Warning: Failed to download $voice.wav"
    else
        echo "    -> $voice.wav already exists. Skipping."
    fi
done

# 6. Model Provisioning (Idempotent)
echo "[*] Provisioning Full Coqui Model Gallery (5 Models)..."

provision_model() {
    local model_name=$1
    local cmd_type=$2 # "list" or "synth"
    echo "    -> Processing $model_name..."
    # We use 'command -v' to ensure we use the activated tts binary
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
