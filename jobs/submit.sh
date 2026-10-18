#!/usr/bin/env bash
# Submit the Cosmos generation job to Nebius Serverless Jobs.
# Usage: jobs/submit.sh <input-bucket> <output-bucket>
#   buckets are Nebius Object Storage bucket names/IDs; upload out/cosmos/* to the input bucket first.
# ponytail: one GPU, samples run sequentially (~80 s each on H100). Shard across jobs if packs get big.
set -euo pipefail
[ -f "$(dirname "$0")/../.env" ] && set -a && . "$(dirname "$0")/../.env" && set +a
: "${HF_TOKEN:?export HF_TOKEN (Hugging Face read token, Cosmos license accepted)}"
IN=${1:?input bucket}; OUT=${2:?output bucket}

nebius ai job create \
  --name "nearmiss-cosmos-$(date +%m%d-%H%M)" \
  --image nvidia/cuda:12.8.1-devel-ubuntu24.04 \
  --container-command bash \
  --args "-c 'bash /input/cosmos_generate.sh'" \
  --env "HF_TOKEN=$HF_TOKEN" \
  --platform "${PLATFORM:-gpu-h100-sxm}" \
  --preset "${PRESET:-1gpu-16vcpu-200gb}" \
  --timeout 4h \
  --volume "$IN:/input:ro" \
  --volume "$OUT:/output:rw"
