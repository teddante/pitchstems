$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    Write-Host $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

$gpuConstraints = Join-Path $PSScriptRoot "..\constraints\windows-gpu.txt"

Invoke-Checked "Checking Python 3.10..." { & py -3.10 -c "import sys; print(sys.executable)" }

Invoke-Checked "Checking NVIDIA driver..." { & nvidia-smi }

Invoke-Checked "Creating virtual environment..." { & py -3.10 -m venv .venv }

Invoke-Checked "Installing latest pip..." { & .\.venv\Scripts\python -m pip install -U pip }

Invoke-Checked "Installing PitchStems with Windows GPU dependencies..." {
    & .\.venv\Scripts\python -m pip install -c $gpuConstraints -e ".[win-gpu,gui,dev]"
}

Invoke-Checked "Removing default CPU ML wheels..." {
    & .\.venv\Scripts\python -m pip uninstall -y torch torchvision onnxruntime onnxruntime-gpu
}

Invoke-Checked "Installing Windows CUDA PyTorch wheels..." {
    & .\.venv\Scripts\python -m pip install -c $gpuConstraints torch torchvision --index-url https://download.pytorch.org/whl/cu128
}

# Basic Pitch declares a dependency on the `onnxruntime` distribution. Keep that
# metadata installed, then install `onnxruntime-gpu` last so CUDA providers are
# available at runtime. Version pins live in constraints/windows-gpu.txt.
Invoke-Checked "Installing ONNX Runtime metadata package..." {
    & .\.venv\Scripts\python -m pip install -c $gpuConstraints onnxruntime
}

Invoke-Checked "Installing ONNX Runtime GPU package..." {
    & .\.venv\Scripts\python -m pip install -c $gpuConstraints "onnxruntime-gpu[cuda,cudnn]"
}

Invoke-Checked "Checking installed package metadata..." { & .\.venv\Scripts\python -m pip check }

Invoke-Checked "Running GPU doctor..." { & .\.venv\Scripts\pitchstems --doctor --gpu }
