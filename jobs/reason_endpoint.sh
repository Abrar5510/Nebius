#!/usr/bin/env bash
# Deploy Cosmos Reason 2 (8B) as a Nebius Serverless Endpoint with vLLM's OpenAI-compatible server.
# Afterwards: export COSMOS_REASON_URL=http://<endpoint-ip>:8000  (and COSMOS_REASON_KEY if you set --auth)
set -euo pipefail
[ -f "$(dirname "$0")/../.env" ] && set -a && . "$(dirname "$0")/../.env" && set +a
: "${HF_TOKEN:?export HF_TOKEN (Hugging Face read token, Cosmos license accepted)}"

nebius ai endpoint create \
  --name nearmiss-reason \
  --image vllm/vllm-openai:v0.11.0 \
  --container-command vllm \
  --args "serve nvidia/Cosmos-Reason2-8B --max-model-len 16384 --reasoning-parser qwen3 --media-io-kwargs '{\"video\": {\"num_frames\": -1}}'" \
  --container-port 8000 \
  --env "HF_TOKEN=$HF_TOKEN" \
  --platform "${PLATFORM:-gpu-l40s-a}" \
  --preset "${PRESET:-1gpu-8vcpu-32gb}" \
  --public
