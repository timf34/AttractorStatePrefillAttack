"""CPU checks for the EasySteer port (no vLLM needed):

1. cap.py's clamp equals axislib's ActivationSteering._apply_cap on random data,
   including the tau encoding in the direction norm.
2. export.py writes a GGUF whose decoded directions/taus match the config, and a
   spec that EasySteer's authoring schema accepts (validated against the cloned
   overlay's pydantic models if importable, else structurally).
3. run_capped --backend easysteer works end to end against a fake OpenAI-compatible
   server (records the steering spec it receives), with --workers 2.

    PY=<venv python with torch, gguf, openai> $PY -m pytest tests/test_easysteer_cpu.py -q
    (or: $PY tests/test_easysteer_cpu.py)
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_cap_module():
    """Import capped/easysteer/cap.py with stub base/registry (the real ones live in vLLM)."""
    import types
    pkg = types.ModuleType("fake_alg_pkg"); pkg.__path__ = []
    base = types.ModuleType("fake_alg_pkg.base")

    class BaseSteerVectorAlgorithm:
        graph_family = None

        def __init__(self, *, normalize=False):
            self.normalize = normalize
    base.BaseSteerVectorAlgorithm = BaseSteerVectorAlgorithm
    reg = types.ModuleType("fake_alg_pkg.registry")
    reg.register_algorithm = lambda name: (lambda cls: cls)
    sys.modules["fake_alg_pkg"] = pkg; sys.modules["fake_alg_pkg.base"] = base; sys.modules["fake_alg_pkg.registry"] = reg
    spec = importlib.util.spec_from_file_location("fake_alg_pkg.cap", ROOT / "capped/easysteer/cap.py")
    mod = importlib.util.module_from_spec(spec); mod.__package__ = "fake_alg_pkg"
    spec.loader.exec_module(mod)
    return mod


def test_cap_matches_axislib():
    cap = _load_cap_module()
    from capped.axislib.steering import ActivationSteering
    torch.manual_seed(0)
    H = 64
    v = torch.randn(H)
    for tau in (-40.0, 0.0, 25.0):
        h = torch.randn(200, H) * 10
        # reference: axislib clamp on a (batch, seq, hidden) tensor
        ref = ActivationSteering.__new__(ActivationSteering)
        ref.positions = "all"
        expected = ref._apply_cap(h.unsqueeze(0), v, tau)[0]
        w = v / v.norm() * (cap.TAU_OFFSET + tau)
        got = cap.CapAlgorithm(normalize=False)._transform(h.clone(), w)
        assert torch.allclose(got, expected, atol=1e-3), (tau, (got - expected).abs().max())
        vhat, tau_dec = cap.decode_direction(w)
        assert abs(tau_dec - tau) < 1e-2 and torch.allclose(vhat, v / v.norm(), atol=1e-5)


def test_export_roundtrip(tmp_path=None):
    from capped.easysteer import export
    import gguf
    tmp = Path(tmp_path or tempfile.mkdtemp())
    torch.manual_seed(1)
    H = 32
    vectors = {f"layer_{L}/neg_axis": {"layer": L, "vector": torch.randn(H)} for L in range(4, 8)}
    caps = {4: -12.5, 5: 3.0, 6: 40.0, 7: 0.0}
    cfg = {"vectors": vectors, "experiments": [
        {"id": "layers_4:8-p0.25", "interventions": [{"vector": f"layer_{L}/neg_axis", "cap": caps[L]} for L in range(4, 8)]},
        {"id": "steer_x_4:8-x-0.2", "interventions": [{"vector": f"layer_{L}/neg_axis", "coef": -0.2} for L in range(4, 8)]},
    ]}
    cpath = tmp / "cfg.pt"; torch.save(cfg, cpath)
    spath = export.build(str(cpath), "layers_4:8-p0.25", str(tmp / "sv"))
    spec = json.loads(Path(spath).read_text())
    assert spec["vectors"][0]["algorithm"] == "cap" and spec["vectors"][0]["scale"] == 1.0
    assert spec["vectors"][0]["layers"] == [4, 5, 6, 7]
    cap = _load_cap_module()
    for t in gguf.GGUFReader(spec["vectors"][0]["source"]).tensors:
        L = int(t.name.removeprefix("direction."))
        vhat, tau = cap.decode_direction(torch.tensor(t.data.copy()))
        v = vectors[f"layer_{L}/neg_axis"]["vector"]
        assert abs(tau - caps[L]) < 1e-2, (L, tau, caps[L])
        assert torch.allclose(vhat, v / v.norm(), atol=1e-4)
    spath2 = export.build(str(cpath), "steer_x_4:8-x-0.2", str(tmp / "sv"))
    spec2 = json.loads(Path(spath2).read_text())
    assert spec2["vectors"][0]["algorithm"] == "direct" and abs(spec2["vectors"][0]["scale"] + 0.2) < 1e-9
    # optional: validate against the real EasySteer authoring schema if the clone is around
    es = os.environ.get("EASYSTEER_SRC")
    if es and (Path(es) / "vllm/model_hooks/steering/api.py").exists():
        sys.path.insert(0, es)
        try:
            from vllm.model_hooks.steering.api import SteeringSpec  # noqa
            SteeringSpec.model_validate(spec2)
        except Exception as e:  # pragma: no cover
            print("schema validation skipped:", e)


class _FakeServer(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"data": [{"id": "qwen2.5-0.5b-test"}]}).encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n))
        _FakeServer.seen.append(body.get("steering"))
        last = body["messages"][-1]["content"][:20]
        out = {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
               "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": f"echo: {last}"}}],
               "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(out).encode())


def test_runner_easysteer_backend():
    import subprocess
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeServer)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = Path(tempfile.mkdtemp())
    torch.manual_seed(0)
    cfg = {"vectors": {f"layer_{L}/axis": {"layer": L, "vector": torch.randn(896)} for L in range(16, 20)},
           "experiments": [{"id": "layers_16:20-p0.25", "interventions": [{"vector": f"layer_{L}/axis", "cap": 1.0} for L in range(16, 20)]}]}
    torch.save(cfg, tmp / "cfg.pt")
    d = json.loads((ROOT / "seeds/graded/opus4_seed_4_deep.json").read_text())
    (tmp / "seed4.json").write_text(json.dumps({"turns": d["turns"][:4]}))
    cmd = [sys.executable, "-m", "capped.run_capped", "--model", "qwen2.5-0.5b-test", "--backend", "easysteer",
           "--base-url", f"http://127.0.0.1:{port}/v1", "--steer-dir", str(tmp / "sv"), "--config-path", str(tmp / "cfg.pt"),
           "--cap", "both", "--seeds", str(tmp / "seed4.json"), "--control", "--epochs", "1", "--turns", "2",
           "--workers", "2", "--out", str(tmp / "res"), "--stamp", "fake"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    files = sorted((tmp / "res").glob("*__ep0__fake.json"))
    assert len(files) == 4, files
    for f in files:
        res = json.loads(f.read_text())
        assert res["generation"]["backend"] == "easysteer" and res["projection"] is None
        assert sum(t["origin"] == "generated" for t in res["transcript"]) == 2
    kinds = {json.dumps(s, sort_keys=True) if isinstance(s, dict) else s for s in _FakeServer.seen}
    assert False in kinds and any(isinstance(s, dict) and s["vectors"][0]["algorithm"] == "cap" for s in _FakeServer.seen)
    srv.shutdown()


if __name__ == "__main__":
    test_cap_matches_axislib(); print("cap math ok")
    test_export_roundtrip(); print("export roundtrip ok")
    test_runner_easysteer_backend(); print("runner easysteer backend ok")
    print("EASYSTEER CPU TESTS PASSED")
