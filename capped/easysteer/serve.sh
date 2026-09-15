#!/usr/bin/env bash
# Start an EasySteer vLLM server for one of our models, steering enabled for "cap" and
# "direct", per-request specs (no engine default). Blocks until /v1/models answers.
#
#   bash capped/easysteer/serve.sh gemma-4-31b            # -> http://localhost:8000/v1
#   PORT=8001 MAX_MODEL_LEN=32768 bash capped/easysteer/serve.sh qwen3-32b
#   bash capped/easysteer/serve.sh stop
#
# Sizing: our deep-prefill episodes reach ~26-30k tokens (15k prefill + 15 turns of up to 1k),
# so MAX_MODEL_LEN defaults to 40960. Llama 70B bf16 needs TP over 2x80GB and then has ~20GB
# of KV: 1-2 concurrent conversations; Gemma/Qwen fit 4-8 on 2 GPUs. MAX_NUM_SEQS bounds that.
# --disable-custom-all-reduce: TP=2 died with custom_all_reduce.cuh 'invalid argument' on a RunPod
# H200 pair without peer access (2026-09-14); NCCL all-reduce works everywhere.
set -uo pipefail
DRV=$(nvidia-smi 2>/dev/null | grep -oE 'CUDA Version: [0-9]+\.[0-9]+' | grep -oE '[0-9]+' | head -1)
ES_VENV="${ES_VENV:-$([ "${DRV:-13}" = 12 ] && echo /workspace/es_venv_cu128 || echo /workspace/es_venv)}"
PORT="${PORT:-8000}"
LOG="${LOG:-/workspace/es_server.log}"
export HF_HOME="${HF_HOME:-/workspace/hf}" HF_HUB_DISABLE_XET=1

stop_server() {
  pkill -f "vllm serve" 2>/dev/null || true
  for _ in $(seq 1 30); do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
    [ -z "$used" ] || [ "$used" -lt 2000 ] && return 0
    pkill -9 -f "vllm" 2>/dev/null || true; sleep 4
  done
}
[ "${1:-}" = "stop" ] && { stop_server; echo "server stopped"; exit 0; }
MODEL_KEY="${1:?model key}"
case "$MODEL_KEY" in
  gemma-4-31b)   HF=google/gemma-4-31B-it;             TEMPLATE="" ;;
  qwen3-32b)     HF=Qwen/Qwen3-32B;                     TEMPLATE="qwen3_no_thinking" ;;
  llama-3.3-70b) HF=meta-llama/Llama-3.3-70B-Instruct;  TEMPLATE="" ;;
  *) echo "unknown model key $MODEL_KEY"; exit 1 ;;
esac
NGPU=$(nvidia-smi -L | wc -l | tr -d ' ')
MAX_MODEL_LEN="${MAX_MODEL_LEN:-40960}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-8}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.92}"
# QUANT=fp8: vLLM quantises the bf16 checkpoint to FP8 weights at load (activations stay bf16),
# so Llama 70B (140 GB bf16) fits one H200 with room for KV. Used for the 1-GPU Llama steering run.
QUANT_FLAG="${QUANT:+--quantization $QUANT}"
TEMPLATE_FLAG=""
if [ "$TEMPLATE" = "qwen3_no_thinking" ]; then
  # pin thinking off at template level (matches the OpenRouter/HF runs: enable_thinking=False)
  "$ES_VENV/bin/python" - "$HF" <<'PY'
import sys
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(sys.argv[1])
open("/workspace/qwen3_no_thinking.jinja", "w").write("{%- set enable_thinking = false -%}" + tok.chat_template)
PY
  TEMPLATE_FLAG="--chat-template /workspace/qwen3_no_thinking.jinja"
fi
stop_server
# shellcheck disable=SC2086
PATH="$ES_VENV/bin:$PATH" nohup "$ES_VENV/bin/vllm" serve "$HF" --served-model-name "$MODEL_KEY" $TEMPLATE_FLAG \
  --tensor-parallel-size "$NGPU" --max-model-len "$MAX_MODEL_LEN" --max-num-seqs "$MAX_NUM_SEQS" \
  --gpu-memory-utilization "$GPU_MEM_UTIL" --port "$PORT" \
  --enable-steer-vector --steer-algorithms cap,direct --steer-graph-mode split \
  --disable-custom-all-reduce $QUANT_FLAG \
  > "$LOG" 2>&1 &
echo "vllm serve pid $! (log $LOG)"
# Readiness wait: a volume-less pod downloads weights first (Llama 70B = 140 GB took >20 min on 2026-09-14 and the old 20-min limit killed the batch), so default to 60 min.
SERVE_WAIT_MIN="${SERVE_WAIT_MIN:-60}"
for i in $(seq 1 $((SERVE_WAIT_MIN*12))); do
  curl -sf "http://localhost:$PORT/v1/models" 2>/dev/null | grep -q "$MODEL_KEY" && { echo "server up after ~$((i*5))s: http://localhost:$PORT/v1"; exit 0; }
  pgrep -f "vllm serve" >/dev/null || { echo "!! server died"; tail -n 30 "$LOG"; exit 1; }
  sleep 5
done
echo "!! server not up after $SERVE_WAIT_MIN min"; tail -n 30 "$LOG"; exit 1
