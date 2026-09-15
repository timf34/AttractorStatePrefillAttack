#!/usr/bin/env bash
# Llama 3.3 70B steering batch on a FRESH volume-less 2x H200 pod, following the runpod-runner
# cost rules: weights download at boot (hf_transfer, many connections) in parallel with the
# EasySteer install; every step fails loudly (non-zero exit -> the monitor terminates the pod).
#   rp run <pod> --job llama -- bash capped/easysteer/llama_es.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="${HF_HOME:-/workspace/hf}" PYTHONUNBUFFERED=1
HF_REPO=meta-llama/Llama-3.3-70B-Instruct
step() { echo; echo "=== $1  $(date -u +%FT%TZ)"; }

step "download $HF_REPO in the background (hf_transfer)"
# hf_transfer + retries: the plain single-connection path did ~130 MB/s (140 GB = 20 min).
( export HF_HUB_ENABLE_HF_TRANSFER=1 HF_HUB_DISABLE_XET=1
  for i in 1 2 3 4 5; do
    huggingface-cli download "$HF_REPO" --exclude "original/*" >/workspace/dl.log 2>&1 && { echo DL_OK >> /workspace/dl.log; exit 0; }
    echo "download attempt $i failed; retrying" >> /workspace/dl.log; sleep 10
  done; echo DL_FAILED >> /workspace/dl.log; exit 1 ) &
DL_PID=$!

step "install EasySteer + cap algorithm"
bash capped/easysteer/install.sh || { echo "INSTALL FAILED"; kill $DL_PID 2>/dev/null; exit 1; }

step "wait for download"
wait $DL_PID || { echo "DOWNLOAD FAILED"; tail -n 20 /workspace/dl.log; exit 1; }
echo "download done: $(du -sh /workspace/hf/hub/models--meta-llama--Llama-3.3-70B-Instruct | cut -f1)"

step "steering batch (subtract_es.sh, Llama only)"
# 2x H200, bf16 (set QUANT=fp8 SKIP_ACTS=1 for a 1-GPU run without the activation pass).
HF_HUB_DISABLE_XET=1 MODELS=llama-3.3-70b bash capped/easysteer/subtract_es.sh || exit 1
grep -q "SERVE FAILED" /workspace/llama.log 2>/dev/null && { echo "batch skipped a model"; exit 1; }
echo "LLAMA ES DONE $(date -u +%FT%TZ)"
