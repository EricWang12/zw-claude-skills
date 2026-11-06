#!/usr/bin/env bash
# First use on a machine: build the WhisperX env, download the models and run them once.
# Usage: bash setup.sh [VENV]      (default: $TRANSCRIBE_MEETING_VENV, else ~/.local/share/transcribe-meeting/venv)
# Safe to rerun: an env that already passed the warm-up is reused in seconds.
# Installs only into VENV (and uv into ~/.local/bin if missing). Drivers and system CUDA are untouched.
# Prints SETUP_READY venv=<path> at the end; pass that path to env.sh (it also puts ffmpeg on PATH).
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV="${1:-${TRANSCRIBE_MEETING_VENV:-$HOME/.local/share/transcribe-meeting/venv}}"
mkdir -p "$(dirname -- "$VENV")"
VENV="$(cd -- "$(dirname -- "$VENV")" && pwd -P)/$(basename -- "$VENV")"
[[ -L "$VENV" ]] && VENV="$(readlink -f -- "$VENV")"
HOME_DIR="$(dirname -- "$VENV")"

if [[ -f "$VENV/.warmup-ok" ]] && "$VENV/bin/python" -c "import whisperx" 2>/dev/null; then
    echo "SETUP_READY venv=$VENV (already set up)"; exit 0
fi

command -v nvidia-smi >/dev/null || { echo "FAIL no nvidia-smi: this needs an NVIDIA GPU" >&2; exit 1; }
free_gb=$(df -Pk "$HOME_DIR" | awk 'NR==2{print int($4/1048576)}')
(( free_gb >= 20 )) || { echo "FAIL $HOME_DIR has ${free_gb} GB free; need ~20 GB. Pass a VENV path on a bigger disk." >&2; exit 1; }

if ! command -v uv >/dev/null; then
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
fi

# No system ffmpeg: use a static build in $HOME_DIR/bin (env.sh puts it on PATH). No apt, no sudo.
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
    if [[ ! -x "$HOME_DIR/bin/ffprobe" ]]; then
        [[ "$(uname -m)" == x86_64 ]] || { echo "FAIL no ffmpeg and no static build for $(uname -m)" >&2; exit 1; }
        echo "No system ffmpeg: fetching a static build into $HOME_DIR/bin"
        mkdir -p "$HOME_DIR/bin"
        curl -LsSf https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
            | tar -xJ -C "$HOME_DIR/bin" --strip-components=1 --wildcards '*/ffmpeg' '*/ffprobe'
    fi
    export PATH="$HOME_DIR/bin:$PATH"
fi

export UV_CACHE_DIR="$HOME_DIR/.cache/uv"
if ! "$VENV/bin/python" -c "import whisperx" 2>/dev/null; then
    echo "Installing WhisperX into $VENV (several minutes; log: $HOME_DIR/install.log)"
    uv venv --python 3.12 "$VENV" > "$HOME_DIR/install.log" 2>&1
    # Known-good baseline from references/setup.md (cu128 wheels cover Blackwell).
    uv pip install --python "$VENV/bin/python" --index-strategy unsafe-best-match \
        --extra-index-url https://download.pytorch.org/whl/cu128 \
        'whisperx==3.8.6' 'torch==2.8.0+cu128' 'torchaudio==2.8.0+cu128' \
        'torchvision==0.23.0+cu128' 'ctranslate2==4.8.5' 'transformers<5' >> "$HOME_DIR/install.log" 2>&1 \
        || { tail -20 "$HOME_DIR/install.log" >&2; echo "FAIL install; see $HOME_DIR/install.log" >&2; exit 1; }
    uv pip freeze --python "$VENV/bin/python" > "$HOME_DIR/packages.txt"
fi

# First launch: download large-v3, Silero VAD and the zh/en aligners, and run them on the GPU.
source "$HERE/env.sh" "$VENV"
python - <<'EOF'
import numpy as np, torch, whisperx
assert torch.cuda.is_available(), "torch sees no CUDA GPU"
model = whisperx.load_model("large-v3", "cuda", compute_type="float16", vad_method="silero", threads=8)
t = np.arange(16000 * 3) / 16000
audio = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
model.transcribe(audio, batch_size=1, language="en")           # exercises the CUDA/cuDNN path
for lang in ("en", "zh"):
    whisperx.load_align_model(language_code=lang, device="cuda")
print("warm-up ok:", torch.cuda.get_device_name(0))
EOF
touch "$VENV/.warmup-ok"
echo "SETUP_READY venv=$VENV"
