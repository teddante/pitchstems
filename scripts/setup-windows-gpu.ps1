$ErrorActionPreference = "Stop"

Write-Host "Checking Python 3.10..."
py -3.10 -c "import sys; print(sys.executable)"

Write-Host "Checking NVIDIA driver..."
nvidia-smi

Write-Host "Creating virtual environment..."
py -3.10 -m venv .venv

Write-Host "Installing PitchStems with Windows GPU dependencies..."
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[win-gpu,gui,dev]"

Write-Host "Replacing default CPU ML wheels with Windows CUDA wheels..."
.\.venv\Scripts\python -m pip uninstall -y torch torchvision onnxruntime onnxruntime-gpu
.\.venv\Scripts\python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python -m pip install "onnxruntime-gpu[cuda,cudnn]>=1.23.2"

Write-Host "Running GPU doctor..."
.\.venv\Scripts\pitchstems --doctor --gpu
