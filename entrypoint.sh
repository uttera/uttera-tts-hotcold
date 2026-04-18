#!/bin/bash
# Coqui TTS Server - Docker Entrypoint
# Provisions model and standard voices on first run, then starts the server.
set -e

ASSETS_DIR="/app/assets"
MODELS_DIR="$ASSETS_DIR/models"
VOICES_STANDARD_DIR="$ASSETS_DIR/voices/standard"
VOICES_ELITE_DIR="$ASSETS_DIR/voices/elite"
CACHE_DIR="$ASSETS_DIR/cache"

mkdir -p "$MODELS_DIR" "$VOICES_STANDARD_DIR" "$VOICES_ELITE_DIR" "$CACHE_DIR"

export TTS_HOME="$MODELS_DIR"
export COQUI_TOS_AGREED=1

MODEL_NAME="${TTS_MODEL:-tts_models/multilingual/multi-dataset/xtts_v2}"

# Coqui stores models with slashes replaced by '--'
MODEL_DIR_NAME=$(echo "$MODEL_NAME" | tr '/' '--')

# --- Model provisioning ---
if [ ! -d "$MODELS_DIR/$MODEL_DIR_NAME" ]; then
    echo "[entrypoint] Model not found. Downloading: $MODEL_NAME ..."
    /app/venv/bin/tts --model_name "$MODEL_NAME" --list_language_idxs > /dev/null 2>&1 || true
    echo "[entrypoint] Model download complete."
else
    echo "[entrypoint] Model already cached at $MODELS_DIR/$MODEL_DIR_NAME"
fi

# --- Standard voices provisioning ---
VOICE_BASE_URL="https://cdn.openai.com/API/docs/audio"
voices=("alloy" "echo" "fable" "onyx" "nova" "shimmer")

for voice in "${voices[@]}"; do
    TARGET="$VOICES_STANDARD_DIR/$voice.wav"
    if [ ! -f "$TARGET" ]; then
        echo "[entrypoint] Downloading voice: $voice ..."
        # -4: force IPv4 — Azure CDN blocks IPv6 from HE tunnel broker ASNs
        curl -L -s -4 -o "$TARGET" "$VOICE_BASE_URL/$voice.wav"
        # Validate
        MIME=$(file --mime-type -b "$TARGET" 2>/dev/null || echo "unknown")
        if [[ "$MIME" != *"audio/"* ]]; then
            echo "[entrypoint] WARNING: $voice.wav failed validation ($MIME). Removing."
            rm -f "$TARGET"
        else
            echo "[entrypoint] Voice $voice.wav ready."
        fi
    fi
done

echo "[entrypoint] Assets ready. Starting server..."
exec /app/venv/bin/uvicorn main_tts:app --host 0.0.0.0 --port 9004
