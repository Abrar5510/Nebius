#!/usr/bin/env bash
# Runs INSIDE a Nebius Serverless Job (stock CUDA 12.8 image, 1x H100/L40S).
# /input  : bucket with *.json Cosmos sample files + their lead-in .mp4s (written by `nearmiss prep`)
# /output : bucket where generated .mp4s land
# Needs HF_TOKEN with the NVIDIA Open Model License accepted on Hugging Face.
# Guardrails stay ON: the NVIDIA Open Model License does not allow switching them off.
set -euo pipefail

apt-get update -qq && apt-get install -y -qq git git-lfs curl ffmpeg libx11-dev >/dev/null
curl -LsSf https://astral.sh/uv/install.sh | sh && source "$HOME/.local/bin/env"

git clone -q https://github.com/nvidia-cosmos/cosmos-predict2.5.git /cosmos
cd /cosmos && git lfs pull
uv python install && uv sync --extra=cu128 -q

export HF_HOME=/output/.hf  # cache weights in the bucket so re-runs skip the ~20 GB download
mkdir -p /output/gen
uv run python examples/inference.py -i /input/*.json -o /output/gen --inference-type=video2world
ls -la /output/gen
