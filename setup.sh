#!/bin/bash
cd "$(dirname "$0")"

echo "========================================"
echo "  Exam Project - Environment Setup"
echo "========================================"
echo

PYTHON_CMD=""

# 1. Check portable Python
if [ -f "./python_portable/bin/python3" ]; then
    echo "[Info] Portable Python found, skipping download."
    PYTHON_CMD="./python_portable/bin/python3"
# 2. Check system Python
elif command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    if [ "$(printf '%s\n' "3.11" "$PY_VERSION" | sort -V | head -n1)" = "3.11" ]; then
        echo "[Info] Using system python3:"
        python3 --version
        echo
        PYTHON_CMD="python3"
    else
        echo "[Error] Found python3 but version is $PY_VERSION (need 3.11+)."
        echo "  macOS:  brew install python@3.11"
        echo "  Ubuntu: sudo apt install python3.11 python3-venv"
        exit 1
    fi
elif command -v python &>/dev/null; then
    PY_VERSION=$(python -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    if [ "$(printf '%s\n' "3.11" "$PY_VERSION" | sort -V | head -n1)" = "3.11" ]; then
        echo "[Info] Using system python:"
        python --version
        echo
        PYTHON_CMD="python"
    fi
else
    echo "[Error] Python 3.11+ not found."
    echo "  macOS:  brew install python@3.11"
    echo "  Ubuntu: sudo apt install python3.11"
    exit 1
fi

echo "[Using] $PYTHON_CMD"
echo

# 3. Install dependencies
echo "[Install] Dependencies ..."
echo

export PYTHONPATH="$(pwd)/src:${PYTHONPATH}"

"$PYTHON_CMD" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn 2>/dev/null
"$PYTHON_CMD" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if [ $? -ne 0 ]; then
    echo "[Error] Failed to install dependencies."
    exit 1
fi

echo
echo "========================================"
echo "Setup completed successfully!"
echo "========================================"
echo
echo "Next step:"
echo "  streamlit run app.py"
echo
