#!/bin/zsh
# Fourth prefill depth: 8 turns of pure philosophical exchange (cut after turn 7,
# before the first gratitude at turn 9). n=6 on the 12 full-grid models. Resumable.
cd "$(dirname "$0")"; set -a; source .env; set +a
STAMP=20260903-philo
SEED=seeds/graded/opus4_seed_4_philo.json
for m in deepseek-v4 gemini-3.1-pro gemini-3.8-flash glm-5.2 gpt-4.1 gpt-5.1 gpt-5.5 kimi-k2.6 llama-3.3-70b inkling opus-4.5 opus-4.8; do
  .venv/bin/python run.py --models $m --seeds $SEED --epochs 6 --turns 15 --workers 3 --stamp $STAMP &
done
wait
echo "PHILO SWEEP COMPLETE $(date)"
