# Environment setup

`scripts/setup.sh` does all of this on first use. Read this only when it fails, or to
choose versions for a new GPU generation.

## Inspect before installing

```bash
nvidia-smi                                   # GPUs, driver, free memory, utilization, other users' jobs
nvidia-smi --query-gpu=index,uuid,name,memory.free,utilization.gpu,compute_cap --format=csv
python3.12 --version || python3.11 --version
ffmpeg -version | head -1
df -h .                                      # the env (~8 GB) and models (~6 GB) need room
```

The CUDA version that `nvidia-smi` reports is the newest version the driver supports. It is
not the CUDA runtime that PyTorch uses. Choose the PyTorch wheel index for the GPU
generation: Blackwell (compute capability 12.x) needs cu128 or newer wheels.

## Where to put the environment

Put it on a disk with room. Do not use a nearly full home directory. `env.sh` keeps the
model caches next to the env (`<env parent>/.cache/`), so later runs reuse the downloaded
models. Use one dedicated env and do not install into an existing research env.

## Install (baseline that worked on 2026-11-05)

Check the current upstream requirements first:
[WhisperX](https://github.com/m-bain/whisperX), [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[CTranslate2 releases](https://github.com/OpenNMT/CTranslate2/releases). The versions below
are a known-good starting point, not a permanent pin.

```bash
cd /path/with/space
uv venv --python python3.12 .venv-whisperx
UV_CACHE_DIR="$PWD/.cache/uv" uv pip install --python .venv-whisperx/bin/python \
  --index-strategy unsafe-best-match \
  --extra-index-url https://download.pytorch.org/whl/cu128 \
  'whisperx==3.8.6' 'torch==2.8.0+cu128' 'torchaudio==2.8.0+cu128' \
  'torchvision==0.23.0+cu128' 'ctranslate2==4.8.5' 'transformers<5' > install.log 2>&1
uv pip check --python .venv-whisperx/bin/python
.venv-whisperx/bin/pip freeze > packages.txt 2>/dev/null || uv pip freeze --python .venv-whisperx/bin/python > packages.txt
```

Wait for the install to finish before you check anything. Then run
`source $S/env.sh .venv-whisperx` and `sample_check.py`. Only the gate shows whether the
stack works.

| Component | Tested value |
|---|---|
| GPU | RTX PRO 6000 Blackwell (compute capability 12.0), driver 580.159.04 |
| Python | 3.12.3 |
| whisperx / faster-whisper / ctranslate2 | 3.8.6 / 1.2.1 / 4.8.5 |
| torch / torchaudio / torchvision | 2.8.0+cu128 / 2.8.0+cu128 / 0.23.0+cu128 (cuDNN 9.10.2) |
| transformers / pyannote.audio | 4.57.6 / 4.0.7 |
| ASR model | `Systran/faster-whisper-large-v3` (downloads on first use, ~3 GB) |
| Chinese aligner | `jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn` |

The first run needs network access. It downloads the Whisper model, the Silero VAD (via
torch.hub from GitHub) and the aligners. Later runs use the caches.

## Troubleshooting the gate

| Failure | Fix |
|---|---|
| `torch.cuda.is_available()` is False | Wrong wheel index, or the chosen GPU is not visible. Check `CUDA_VISIBLE_DEVICES` from env.sh |
| `no kernel image is available` | The torch build lacks this GPU's architecture. Use a newer cuXXX wheel |
| `libcudnn*.so` / `libcublas*.so` not found during Whisper inference | CTranslate2 uses the cuDNN/cuBLAS pip wheels. `env.sh` adds `site-packages/nvidia/*/lib` to `LD_LIBRARY_PATH`. Source it in the same shell |
| CTranslate2 lacks `float16` on CUDA | The CTranslate2 build does not match the CUDA/cuDNN major version. Install a compatible ctranslate2 release |
| CUDA out of memory | Another job uses the GPU. Pass a different GPU UUID to env.sh, or use a smaller `--batch-size` |

Whisper large-v3 in float16 needs about 5–6 GB of VRAM at batch 8. The alignment and
diarization models load one at a time after ASR.

## Speaker diarization access (optional)

The model `pyannote/speaker-diarization-community-1` is gated. The user must:
1. Accept its conditions at https://huggingface.co/pyannote/speaker-diarization-community-1.
2. Make a read token at https://huggingface.co/settings/tokens. A fine-grained token
   needs access to public gated repositories.
3. Provide it locally: `export HF_TOKEN=...` in their shell, or `hf auth login`.

Never ask the user to paste a token into the chat. Never write a token into a script or log.
