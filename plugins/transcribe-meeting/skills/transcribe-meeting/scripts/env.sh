#!/usr/bin/env bash
# Usage: source env.sh /path/to/.venv-whisperx [GPU_UUID]
# Process-local settings only: PATH, CUDA libraries from the venv's pip wheels,
# model caches next to the venv, telemetry off. Drivers and other envs are untouched.
# Without a GPU argument it picks the GPU with the most free memory right now.
MT_VENV="$(cd -- "${1:?usage: source env.sh VENV [GPU_UUID]}" && pwd -P)"
MT_HOME="$(dirname -- "$MT_VENV")"
export PATH="$MT_VENV/bin:$MT_HOME/bin:$PATH"     # $MT_HOME/bin: static ffmpeg from setup.sh, if any
if [[ -n "${2:-}" ]]; then
    export CUDA_VISIBLE_DEVICES="$2"
else
    export CUDA_VISIBLE_DEVICES="$(nvidia-smi --query-gpu=memory.free,utilization.gpu,uuid \
        --format=csv,noheader,nounits | sort -t, -k1,1nr -k2,2n | head -1 | awk -F', ' '{print $3}')"
fi
MT_SITE="$(ls -d "$MT_VENV"/lib/python3.*/site-packages | head -1)"
MT_LIBS="$(ls -d "$MT_SITE"/nvidia/*/lib "$MT_SITE"/torch/lib 2>/dev/null | paste -sd:)"
export LD_LIBRARY_PATH="$MT_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export HF_HUB_CACHE="$MT_HOME/.cache/huggingface/hub"
export TORCH_HOME="$MT_HOME/.cache/torch"
export NLTK_DATA="$MT_HOME/.cache/nltk_data"
export UV_CACHE_DIR="$MT_HOME/.cache/uv"
export HF_HUB_DISABLE_TELEMETRY=1 PYANNOTE_METRICS_ENABLED=0 DO_NOT_TRACK=1
export TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8
echo "venv=$MT_VENV gpu=$CUDA_VISIBLE_DEVICES"
nvidia-smi --id="$CUDA_VISIBLE_DEVICES" --query-gpu=name,memory.used,memory.free,utilization.gpu --format=csv,noheader
