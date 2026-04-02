#!/bin/bash
# Uttera TTS Unified Setup Script
# Version: 1.1.2 (Local Fix)
# Description: Orchestrates Python environment setup with specific patches for 3.14 compatibility.

set -e

echo "🦾 Uttera - Starting Unified Installation Protocol..."

# 1. Python Virtual Environment
echo "[*] Initializing Python Virtual Environment..."
python3 -m venv venv
source venv/bin/activate

# 2. Pre-installation for Python 3.14 stability
echo "[*] Installing build-time dependencies..."
pip install --upgrade pip setuptools wheel

# 3. Core Dependencies
echo "[*] Installing core dependencies from requirements.txt..."
pip install -r requirements.txt

# 4. Patch transformers for 3.14 compatibility
# NOTE (v1.4.5): This patch is now also applied as a Python monkey-patch in main_tts.py
# (before the TTS import), making it resilient to venv upgrades. This shell patch
# remains here as a belt-and-suspenders measure but is no longer the primary fix.
echo "[*] Applying compatibility patches to transformers..."
# Search for the file in the venv to ensure we hit the right path
TARGET_FILE=$(find venv -name "pytorch_utils.py" | grep "transformers" | head -n 1)
if [ -f "$TARGET_FILE" ]; then
    if ! grep -q "isin_mps_friendly" "$TARGET_FILE"; then
        echo -e "\ndef isin_mps_friendly(elements, test_elements):\n    import torch\n    return torch.isin(elements, test_elements)\n" >> "$TARGET_FILE"
        echo "    -> Patched transformers/pytorch_utils.py"
    fi
fi

# 5. Trigger Asset Provisioning
if [ -f "./setup_assets.sh" ]; then
    echo "[*] Python environment ready. Handing over to setup_assets.sh..."
    chmod +x setup_assets.sh
    ./setup_assets.sh
else
    echo "[!] ERROR: setup_assets.sh not found."
    exit 1
fi

echo "✅ All systems operational."
