#!/bin/zsh
# Second attractor: the GPT-5.2 "spec factory" transcript (AttractorBench family_sweep run 4,
# 30 turns, 92 version tags) as a deep prefill into every model in fig3b. Same harness as the
# bliss sweep (helpful-assistant system + AI-to-AI instruction on A, 15 generated turns).
# Differences from the bliss runs, on purpose:
#   --max-tokens 2048   GPT-5.2's turns run 2-9k chars; a 1024 cap would truncate templates mid-block.
#   --out results_spec  keeps the bliss results/ directory and plots.py untouched.
# Unjudged here; judge afterwards with the spec rubric (selected automatically by condition name):
#   .venv/bin/python rejudge.py --results-dir results_spec
# Resumable: re-running skips finished cells and continues interrupted ones from their checkpoint.
cd "$(dirname "$0")"; set -a; source .env; set +a
STAMP=${STAMP:-20260910-spec}
EPOCHS=${EPOCHS:-5}
SEED=seeds/graded/gpt52_spec_run4_deep.json
# 11-model subset first (3 Claude spanning the accept/refuse boundary, 3 GPT incl. the seed's own
# family, 5 other labs); n=5 for the ablation (bliss figures are n=10); top up a model with the same stamp if it lands mid-way.
MODELS=(opus-4 sonnet-4.5 opus-4.5 gpt-4.1 gpt-5.1 gpt-5.6 gemini-3.1-pro deepseek-v4 llama-3.3-70b inkling kimi-k2.6)
for m in $MODELS; do
  .venv/bin/python run.py --models $m --seeds $SEED --epochs $EPOCHS --turns 15 --workers 3 \
      --max-tokens 2048 --out results_spec --stamp $STAMP > results_spec/log_$m.log 2>&1 &
done
wait
echo "SPEC SWEEP COMPLETE $(date)"
