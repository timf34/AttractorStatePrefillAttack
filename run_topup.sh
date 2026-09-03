#!/bin/zsh
# Deep-prefill top-up: bring every full-grid model to n=10 on the deep cut
# (matching the Claude ladder), plus Inkling control 2 -> 6 and one extra
# Gemini 3.8 Flash deep (3 probe + 6 grid + 1 = 10). Unjudged; judge with rejudge.py.
# Resumable: re-running skips finished cells and continues interrupted ones.
cd "$(dirname "$0")"; set -a; source .env; set +a
STAMP=20260903-deeptop
SEED=seeds/graded/opus4_seed_4_deep.json
for m in deepseek-v4 gemini-3.1-pro glm-5.2 gpt-4.1 gpt-5.1 gpt-5.5 kimi-k2.6 llama-3.3-70b; do
  .venv/bin/python run.py --models $m --seeds $SEED --epochs 4 --turns 15 --workers 4 --stamp $STAMP &
done
.venv/bin/python run.py --models inkling --seeds $SEED --control --epochs 4 --turns 15 --workers 4 --stamp $STAMP &
.venv/bin/python run.py --models gemini-3.8-flash --seeds $SEED --epochs 1 --turns 15 --workers 1 --stamp $STAMP &
wait
echo "DEEP TOP-UP COMPLETE $(date)"
