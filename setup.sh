#!/bin/bash
# Uttera TTS Unified Setup Script
# Version: 1.1.4
# Description: Orchestrates Python environment setup. Uses Python 3.11 for minimal VRAM
#              footprint (~4.4 GB vs ~8.1 GB with 3.13). Falls back to python3 if
#              python3.11 is not found. Install: sudo apt install python3.11 python3.11-venv

set -e

echo "🦾 Uttera - Starting Unified Installation Protocol..."

# 1. Python Virtual Environment
# Python 3.11 is preferred: measured ~4.4 GB VRAM footprint vs ~8.1 GB with Python 3.13
# for identical torch==2.9.0+cu128 + TTS 0.27.5 stack. Critical for fleet deployments.
echo "[*] Initializing Python Virtual Environment..."
if command -v python3.11 &>/dev/null; then
    PYTHON_BIN=python3.11
    echo "    -> Using python3.11 (optimal VRAM footprint)"
else
    PYTHON_BIN=python3
    echo "    [!] python3.11 not found, falling back to $(python3 --version)."
    echo "    [!] WARNING: Python 3.13+ uses ~8.1 GB VRAM vs ~4.4 GB with Python 3.11."
    echo "    [!] Install: sudo apt install python3.11 python3.11-venv python3.11-dev"
fi
$PYTHON_BIN -m venv venv
source venv/bin/activate

# 2. Build-time dependencies
echo "[*] Installing build-time dependencies..."
pip install --upgrade pip setuptools wheel

# 3. Core Dependencies
echo "[*] Installing core dependencies from requirements.txt..."
pip install -r requirements.txt

# 4. Patch transformers for compatibility (isin_mps_friendly missing in some versions)
# NOTE (v1.4.5): This patch is now also applied as a Python monkey-patch in main_tts.py
# (before the TTS import), making it resilient to venv upgrades. This shell patch
# remains here as a belt-and-suspenders measure but is no longer the primary fix.
echo "[*] Applying compatibility patches to transformers..."
# Search for the file in the venv to ensure we hit the right path
TARGET_FILE=$(find venv -name "pytorch_utils.py" 2>/dev/null | grep "transformers" | head -n 1)
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
