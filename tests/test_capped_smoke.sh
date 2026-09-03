#!/usr/bin/env bash
# CPU smoke test for capped/: calibrate -> run_capped on Qwen2.5-0.5B-Instruct with a
# random axis. Checks the plumbing (chat templates, span alignment, capping hooks,
# projections, resumable result files), not anything scientific.
#   PY=<python with torch+transformers> bash tests/test_capped_smoke.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-python}"
TMP="${TMP:-$(mktemp -d)}"
echo "workdir $TMP"

# random axis (24 layers x 896 hidden) and a 4-turn seed cut from the deep prefill
$PY - "$TMP" <<'EOF'
import json, sys, torch
tmp = sys.argv[1]
torch.manual_seed(0)
torch.save(torch.randn(24, 896), f"{tmp}/axis.pt")
d = json.load(open("seeds/graded/opus4_seed_4_deep.json"))
json.dump({"turns": d["turns"][:4]}, open(f"{tmp}/seed4.json", "w"))
EOF

$PY -m capped.calibrate --model qwen2.5-0.5b-test --axis-path "$TMP/axis.pt" \
  --layers 14:22 --windows 16:20 --max-roles 3 --per-role 2 --batch 4 --max-new-tokens 24 \
  --out "$TMP/test_config.pt" --device cpu

$PY -m capped.run_capped --model qwen2.5-0.5b-test --axis-path "$TMP/axis.pt" \
  --config-path "$TMP/test_config.pt" --cap both --seeds "$TMP/seed4.json" --control \
  --epochs 1 --turns 2 --max-new-tokens 24 --out "$TMP/results" --stamp smoke --device cpu

$PY - "$TMP" <<'EOF'
import json, sys, glob
tmp = sys.argv[1]
files = sorted(glob.glob(f"{tmp}/results/*__ep0__smoke.json"))
assert len(files) == 4, files
for f in files:
    d = json.load(open(f))
    n_gen = sum(t["origin"] == "generated" for t in d["transcript"])
    assert n_gen == 2, (f, n_gen)
    raw = d["projection"]["raw"]
    assert len(raw) == len(d["transcript"]) and all(r is not None for r in raw), f
    if d["intervention"]["type"] == "capping":
        assert "intervened" in d["projection"] and len(d["intervention"]["caps"]) == 4, f
        # every capped layer: intervened projection can only move toward the Assistant
        # (higher on the +axis) relative to raw, never away
        for L in [c["layer"] for c in d["intervention"]["caps"]]:
            for r, i in zip(raw, d["projection"]["intervened"]):
                assert i[str(L)] >= r[str(L)] - 1e-3, (f, L, r[str(L)], i[str(L)])
    print("ok", f.split("/")[-1], "gen turns", n_gen, "target-layer proj",
          [round(r[str(d["projection"]["target_layer"])], 2) for r in raw])
print("SMOKE TEST PASSED")
EOF
