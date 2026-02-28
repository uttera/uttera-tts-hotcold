#!/bin/bash
# Uttera TTS Asset Provisioning Script
# Version: 1.2.0 (No-Sudo, Local Assets)
# Description: Provisions models and standard voices into the local 'assets' directory.

set -e

echo "🦾 Uttera - Provisioning Infrastructure Assets (Local Mode)..."

# 1. Path Discovery
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ASSETS_DIR="$SCRIPT_DIR/assets"
MODELS_DIR="$ASSETS_DIR/models"
VOICES_DIR="$ASSETS_DIR/voices"
CACHE_DIR="$ASSETS_DIR/cache"

# 2. Create Directory Structure (Local, no sudo)
echo "[*] Creating local directory structure in $ASSETS_DIR..."
mkdir -p "$MODELS_DIR"
mkdir -p "$VOICES_DIR/standard"
mkdir -p "$VOICES_DIR/elite"
mkdir -p "$CACHE_DIR"

# 3. Environment Variables (Directing Coqui to local assets)
export TTS_HOME="$MODELS_DIR"
export COQUI_TOS_AGREED=1
VOICE_BASE_URL="https://github.com/matatonic/openedai-speech/raw/v0.17.0/voice_samples"

# 4. Standard Voices Provisioning
echo "[*] Provisioning Standard Voice Gallery into $VOICES_DIR/standard..."
voices=("alloy" "echo" "fable" "onyx" "nova" "shimmer")
for voice in "${voices[@]}"; do
    TARGET_FILE="$VOICES_DIR/standard/$voice.wav"
    
    if [ ! -f "$TARGET_FILE" ]; then
        echo "    -> Downloading $voice.wav..."
        curl -L -s -o "$TARGET_FILE" "$VOICE_BASE_URL/$voice.wav"
        
        # Quick validation
        if [ -f "$TARGET_FILE" ]; then
            MIME=$(file --mime-type -b "$TARGET_FILE")
            if [[ "$MIME" == *"text/html"* ]]; then
                echo "    [!] ERROR: Downloaded HTML instead of WAV for $voice.wav. Removing..."
                rm "$TARGET_FILE"
            else
                echo "    [✓] $voice.wav validated ($MIME)."
            fi
        fi
    fi
done

# 5. Model Provisioning (Idempotent)
# Use the venv tts if available
if [ -f "$SCRIPT_DIR/venv/bin/tts" ]; then
    TTS_BIN="$SCRIPT_DIR/venv/bin/tts"
else
    TTS_BIN="tts"
fi

echo "[*] Provisioning AI Models into $MODELS_DIR..."
provision_model() {
    echo "    -> Checking model: $1"
    $TTS_BIN --model_name "$1" --list_language_idxs > /dev/null 2>&1 || true
}

provision_model "tts_models/multilingual/multi-dataset/xtts_v2"
provision_model "tts_models/en/ljspeech/vits"
provision_model "tts_models/es/css10/vits"

echo "✅ Local Asset Provisioning Complete."
