#!/bin/bash
# Uttera TTS Asset Provisioning Script
# Version: 1.1.7 (Hotfix: Real WAV sources & Cache Dir)

set -e

echo "🦾 Uttera - Provisioning Infrastructure Assets..."

# 1. Path Discovery & Environment Activation
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
    echo "[*] Virtual environment detected. Activating..."
    source "$VENV_ACTIVATE"
    TTS_BIN="tts"
else
    echo "[*] Using system-wide 'tts' binary."
    TTS_BIN="tts"
fi

# 2. System Dependencies
echo "[*] Verifying system dependencies (espeak-ng, curl, file)..."
sudo apt-get update -qq && sudo apt-get install -y -qq espeak-ng curl file

# 3. Directory Structure & Permissions
echo "[*] Creating Uttera directory structure..."
sudo mkdir -p /opt/ai/models/speech/coqui-tts
sudo mkdir -p /opt/ai/assets/voices/standard
sudo mkdir -p /opt/ai/assets/voices/elite
sudo mkdir -p /opt/ai/cache
# Cambiar propietario a claw:claw como solicitó el Señor
sudo chown -R claw:claw /opt/ai/models/speech/
sudo chown -R claw:claw /opt/ai/assets/voices/
sudo chown -R claw:claw /opt/ai/cache/

# 4. Environment Variables & Licensing
export TTS_HOME="/opt/ai/models/speech/coqui-tts"
export COQUI_TOS_AGREED=1
# Nueva URL validada
VOICE_BASE_URL="https://github.com/matatonic/openedai-speech/raw/v0.17.0/voice_samples"

# 5. Standard Voices Provisioning
echo "[*] Provisioning Standard Voice Gallery (Real WAVs)..."
voices=("alloy" "echo" "fable" "onyx" "nova" "shimmer")
for voice in "${voices[@]}"; do
    TARGET_FILE="/opt/ai/assets/voices/standard/$voice.wav"
    
    if [ -f "$TARGET_FILE" ]; then
        MIME=$(file --mime-type -b "$TARGET_FILE")
        if [[ "$MIME" == *"text/html"* ]]; then
            echo "    [!] Corrupt HTML file detected for $voice.wav. Removing..."
            rm "$TARGET_FILE"
        fi
    fi

    if [ ! -f "$TARGET_FILE" ]; then
        echo "    -> Downloading $voice.wav..."
        curl -L -s -o "$TARGET_FILE" "$VOICE_BASE_URL/$voice.wav"
        MIME=$(file --mime-type -b "$TARGET_FILE")
        if [[ "$MIME" == *"text/html"* ]]; then
            echo "    [!] ERROR: Downloaded HTML instead of WAV for $voice.wav."
            rm "$TARGET_FILE"
        else
            echo "    [✓] $voice.wav validated ($MIME)."
        fi
    fi
done

# 6. Model Provisioning (Idempotent)
provision_model() {
    $TTS_BIN --model_name "$1" --list_language_idxs > /dev/null 2>&1 || true
}
provision_model "tts_models/multilingual/multi-dataset/xtts_v2"
provision_model "tts_models/en/ljspeech/vits"
provision_model "tts_models/en/vctk/vits"
provision_model "tts_models/es/css10/vits"
provision_model "tts_models/multilingual/multi-dataset/your_tts"

echo "✅ Infrastructure Provisioning Complete and Validated."
