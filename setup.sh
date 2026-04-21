#!/bin/bash
# uttera-tts-hotcold — Unified Setup Script
# Version: 2.0.0-dev
# Description: Orchestrates Python environment setup and asset provisioning.
#
# Usage:
#   ./setup.sh              # default: Coqui backend
#   ./setup.sh coqui        # explicit Coqui backend
#   ./setup.sh voxcpm       # VoxCPM2 backend

set -e

BACKEND="${1:-coqui}"
REQ_FILE="requirements-${BACKEND}.txt"

if [ ! -f "$REQ_FILE" ]; then
    echo "ERROR: Unknown backend '${BACKEND}' — file ${REQ_FILE} not found."
    echo "Available backends:"
    ls requirements-*.txt 2>/dev/null | sed 's/requirements-//;s/\.txt//'
    exit 1
fi

echo "uttera-tts-hotcold — Installing with backend: ${BACKEND}"
echo "Requirements file: ${REQ_FILE}"
echo "------------------------------------------------------------------------"

# 1. Python Virtual Environment
# Uses system default python3 (3.12+ recommended; 3.14 NOT supported by torch).
echo "[*] Initializing Python Virtual Environment..."
PYTHON_BIN=python3
# Prefer python3.12 if available (3.14 has no torch wheels)
if command -v python3.12 &>/dev/null; then
    PYTHON_BIN=python3.12
fi
echo "    -> Using $($PYTHON_BIN --version)"
$PYTHON_BIN -m venv venv
source venv/bin/activate

# 2. Build-time dependencies
echo "[*] Installing build-time dependencies..."
pip install --upgrade pip setuptools wheel

# 3. Backend-specific dependencies (includes base via -r requirements.txt)
echo "[*] Installing dependencies from ${REQ_FILE}..."
pip install -r "$REQ_FILE"

# 4. Patch transformers for compatibility (Coqui backend only)
# The isin_mps_friendly fix is also applied as a Python monkey-patch in
# cold_worker_tts.py, making it resilient to venv upgrades.
if [ "$BACKEND" = "coqui" ]; then
    echo "[*] Applying compatibility patches to transformers..."
    TARGET_FILE=$(find venv -name "pytorch_utils.py" 2>/dev/null | grep "transformers" | head -n 1)
    if [ -f "$TARGET_FILE" ]; then
        if ! grep -q "isin_mps_friendly" "$TARGET_FILE"; then
            echo -e "\ndef isin_mps_friendly(elements, test_elements):\n    import torch\n    return torch.isin(elements, test_elements)\n" >> "$TARGET_FILE"
            echo "    -> Patched transformers/pytorch_utils.py"
        fi
    fi
fi

# 5. Trigger Asset Provisioning (Coqui downloads model + voices)
if [ -f "./setup_assets.sh" ]; then
    echo "[*] Python environment ready. Handing over to setup_assets.sh..."
    chmod +x setup_assets.sh
    ./setup_assets.sh
else
    echo "[*] No setup_assets.sh found — skipping asset provisioning."
    echo "    (VoxCPM2 downloads models on first run via huggingface_hub)"
fi

echo ""
echo "------------------------------------------------------------------------"
echo "Setup complete. Backend: ${BACKEND}"
echo ""
echo "Start the server with:"
echo "  source venv/bin/activate"
echo "  TTS_BACKEND=${BACKEND} uvicorn main_tts:app --host 127.0.0.1 --port 9004"
echo "------------------------------------------------------------------------"
