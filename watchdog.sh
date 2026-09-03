#!/bin/zsh
# Restart the sweep (and re-judge, if still needed) when they stall — e.g. after
# an internet outage leaves requests hanging. "Stalled" = no checkpoint or log
# activity for STALL_S seconds while the processes are still alive.
cd "$(dirname "$0")"; set -a; source .env; set +a
STALL_S=300
while true; do
  sleep 60
  grep -q "LADDER SWEEP COMPLETE" results/ladder.log 2>/dev/null && { echo "$(date) sweep complete, watchdog exiting"; exit 0; }
  now=$(date +%s)
  newest=$(python3 -c "
import glob,os
fs=glob.glob('results/partial/*.json')+glob.glob('results/*__20260902-232705*.json')
print(int(max(os.path.getmtime(f) for f in fs if os.path.exists(f))))")
  age=$((now-newest))
  if [ $age -gt $STALL_S ]; then
    echo "$(date) stalled ${age}s — restarting"
    pkill -f run_ladder.sh; pkill -f "run.py --models"; sleep 3
    nohup ./run_ladder.sh >> results/ladder.log 2>&1 &
    sleep 120
  fi
done
