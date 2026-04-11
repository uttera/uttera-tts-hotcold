#!/bin/bash
# Uttera TTS Unified Setup Script
# Version: 1.7.0
# Description: Orchestrates Python environment setup and asset provisioning.

set -e

echo "Coqui TTS Server — Starting Installation..."

# 1. Python Virtual Environment
# Uses system default python3 (3.12+ recommended).
echo "[*] Initializing Python Virtual Environment..."
PYTHON_BIN=python3
echo "    -> Using $($PYTHON_BIN --version)"
$PYTHON_BIN -m venv venv
source venv/bin/activate

# 2. Build-time dependencies
echo "[*] Installing build-time dependencies..."
pip install --upgrade pip setuptools wheel

# 3. Core Dependencies
echo "[*] Installing core dependencies from requirements.txt..."
pip install -r requirements.txt

# 4. Patch transformers for compatibility (isin_mps_friendly missing in some versions)
# NOTE: This patch is also applied as a Python monkey-patch in main_tts.py
# (before the TTS import), making it resilient to venv upgrades. This shell patch
# remains as a belt-and-suspenders measure.
echo "[*] Applying compatibility patches to transformers..."
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

echo "All systems operational."
