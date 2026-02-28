#!/bin/bash
# Uttera TTS Unified Setup Script
# Version: 1.1.0
# Description: Orchestrates Python environment setup and triggers asset provisioning.

set -e

echo "🦾 Uttera - Starting Unified Installation Protocol..."

# 1. Python Virtual Environment
echo "[*] Initializing Python Virtual Environment..."
python3 -m venv venv
source venv/bin/activate

# 2. Python Dependencies
echo "[*] Installing core dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# --- HOTFIX: Resolve Transformers/Coqui-TTS compatibility bug ---
echo "Applying Transformers compatibility patch..."
TARGET_FILE=$(find venv -name "autoregressive.py" | grep "tortoise")
if [ ! -z "$TARGET_FILE" ]; then
  sed -i "s/from transformers.pytorch_utils import isin_mps_friendly as isin/import torch\ndef isin(a, b): return torch.isin(a, b)/" "$TARGET_FILE"
  echo "Patch applied successfully."
fi

# 3. Trigger Asset Provisioning
if [ -f "./setup_assets.sh" ]; then
    echo "[*] Python environment ready. Handing over to setup_assets.sh..."
    chmod +x setup_assets.sh
    ./setup_assets.sh
else
    echo "[!] ERROR: setup_assets.sh not found. Infrastructure provisioning aborted."
    exit 1
fi

echo "✅ All systems operational. You can now start the server with: source venv/bin/activate && uvicorn main_tts:app"
