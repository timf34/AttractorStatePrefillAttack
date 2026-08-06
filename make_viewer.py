#!/usr/bin/env python3
"""Build a self-contained HTML viewer for prefill-attack transcripts.

Reads every results/*.json run file and writes transcript_viewer.html with all
data embedded, so the viewer works as a plain local file (no server needed).

Usage: python3 make_viewer.py [--results-dir results] [--out transcript_viewer.html]
"""
import argparse
import json
from pathlib import Path

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prefill Attack Transcript Viewer</title>
<style>
  :root {
    --bg: #faf9f5; --panel: #ffffff; --border: #e4e2dc;
    --ink: #21201d; --ink-2: #5f5d56; --ink-3: #8a877e;
    --accent: #2a78d6;
    --bubble-a: #eef4fc; --bubble-b: #f4f1ea;
    --seed-ink: #8a877e;
    --sel: #e2edfb;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1a19; --panel: #232322; --border: #3a3936;
      --ink: #ececea; --ink-2: #b3b1aa; --ink-3: #85837c;
      --accent: #5598e7;
      --bubble-a: #1f2b3b; --bubble-b: #2b2a26;
      --seed-ink: #85837c;
      --sel: #23364e;
    }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    display: flex; overflow: hidden;
  }
  #sidebar {
    width: 320px; min-width: 240px; flex: none; border-right: 1px solid var(--border);
    display: flex; flex-direction: column; background: var(--panel);
  }
  #sidebar header { padding: 12px 12px 8px; border-bottom: 1px solid var(--border); }
  #sidebar h1 { font-size: 14px; margin: 0 0 8px; }
  #sidebar .filters { display: flex; flex-direction: column; gap: 6px; }
  #sidebar select, #sidebar input[type=search] {
    width: 100%; padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--bg); color: var(--ink); font: inherit; font-size: 13px;
  }
  #count { font-size: 12px; color: var(--ink-3); padding: 6px 12px 2px; }
  #runlist { flex: 1; overflow-y: auto; padding: 4px; }
  .run {
    padding: 7px 9px; border-radius: 8px; cursor: pointer; margin-bottom: 2px;
    border: 1px solid transparent;
  }
  .run:hover { background: var(--bg); }
  .run.active { background: var(--sel); border-color: var(--accent); }
  .run .top { display: flex; justify-content: space-between; gap: 6px; align-items: baseline; }
  .run .model { font-weight: 600; font-size: 13px; }
  .run .cond { color: var(--ink-2); font-size: 12px; }
  .run .meta { display: flex; gap: 6px; align-items: center; margin-top: 2px; font-size: 11px; color: var(--ink-3); }
  .badge {
    display: inline-block; padding: 0 6px; border-radius: 999px; font-size: 10.5px;
    font-weight: 600; line-height: 16px; border: 1px solid var(--border); color: var(--ink-2);
  }
  .badge.captured { background: #d03b3b; border-color: #d03b3b; color: #fff; }
  .badge.escaped  { background: #0ca30c; border-color: #0ca30c; color: #fff; }

  #main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  #runheader { padding: 14px 20px 10px; border-bottom: 1px solid var(--border); background: var(--panel); }
  #runheader h2 { margin: 0 0 2px; font-size: 16px; }
  #runheader .sub { color: var(--ink-2); font-size: 12.5px; }
  #stats { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; font-size: 12.5px; color: var(--ink-2); }
  #stats b { color: var(--ink); font-weight: 600; }

  /* depth heatmap strip */
  #striprow { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
  #strip { display: flex; gap: 2px; flex-wrap: wrap; }
  .cell {
    width: 16px; height: 16px; border-radius: 3px; cursor: pointer;
    border: 1px solid var(--border); position: relative;
  }
  .cell.seedcell { border-style: dashed; }
  .cell:hover { outline: 2px solid var(--accent); outline-offset: 1px; }
  #striplegend { font-size: 11px; color: var(--ink-3); white-space: nowrap; }
  #striplegend .ramp {
    display: inline-block; width: 70px; height: 9px; border-radius: 3px; vertical-align: -1px;
    background: linear-gradient(to right, #cde2fb, #3987e5, #0d366b);
    border: 1px solid var(--border);
  }

  #transcript { flex: 1; overflow-y: auto; padding: 18px 20px 60px; }
  .turn { max-width: 860px; margin: 0 auto 14px; }
  .turnhead {
    display: flex; gap: 8px; align-items: baseline; font-size: 11.5px; color: var(--ink-3);
    margin-bottom: 3px;
  }
  .turnhead .spk { font-weight: 700; color: var(--ink-2); }
  .bubble {
    padding: 10px 14px; border-radius: 10px; white-space: pre-wrap; overflow-wrap: break-word;
    border: 1px solid var(--border);
  }
  .spkA .bubble { background: var(--bubble-a); margin-right: 8%; }
  .spkB .bubble { background: var(--bubble-b); margin-left: 8%; }
  .spkB .turnhead { justify-content: flex-end; }
  .turn.seed .bubble { border-style: dashed; color: var(--seed-ink); }
  .turn.flash .bubble { outline: 2px solid var(--accent); }
  .scoreline { font-size: 11px; color: var(--ink-3); margin-top: 3px; }
  .spkB .scoreline { text-align: right; }
  .judgenote { font-style: italic; }

  #tooltip {
    position: fixed; z-index: 10; pointer-events: none; display: none;
    background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 6px 9px; font-size: 12px; box-shadow: 0 4px 14px rgba(0,0,0,.18);
    max-width: 320px; color: var(--ink);
  }
  #empty { margin: auto; color: var(--ink-3); }
</style>
</head>
<body>
<div id="sidebar">
  <header>
    <h1>Prefill Attack Transcripts</h1>
    <div class="filters">
      <input id="q" type="search" placeholder="Search runs…">
      <select id="fmodel"><option value="">All models</option></select>
      <select id="fcond"><option value="">All conditions</option></select>
      <select id="fcaptured">
        <option value="">Captured + not</option>
        <option value="1">Captured only</option>
        <option value="0">Not captured only</option>
      </select>
    </div>
  </header>
  <div id="count"></div>
  <div id="runlist"></div>
</div>
<div id="main">
  <div id="runheader" hidden>
    <h2 id="rh-title"></h2>
    <div class="sub" id="rh-sub"></div>
    <div id="stats"></div>
    <div id="striprow">
      <div id="strip"></div>
      <div id="striplegend">judge depth 0 <span class="ramp"></span> 10 &nbsp;·&nbsp; dashed = seed turn</div>
    </div>
  </div>
  <div id="transcript"><div id="empty">Select a run on the left.</div></div>
</div>
<div id="tooltip"></div>
<script>
const DATA = __DATA__;

// sequential blue ramp (light -> dark) for depth 0..10
const RAMP = ["#cde2fb","#b7d3f6","#9ec5f4","#86b6ef","#6da7ec","#5598e7",
              "#3987e5","#2a78d6","#256abf","#1c5cab","#0d366b"];
const SEED_FILL = getComputedStyle(document.documentElement) ? null : null;

const $ = id => document.getElementById(id);
const esc = s => s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

DATA.sort((a,b) => a.model.localeCompare(b.model) || a.condition.localeCompare(b.condition)
                 || (a.epoch-b.epoch) || a.file.localeCompare(b.file));

// populate filters
const models = [...new Set(DATA.map(d=>d.model))].sort();
const conds  = [...new Set(DATA.map(d=>d.condition))].sort();
for (const m of models) $("fmodel").insertAdjacentHTML("beforeend", `<option>${esc(m)}</option>`);
for (const c of conds)  $("fcond").insertAdjacentHTML("beforeend", `<option>${esc(c)}</option>`);

let activeIdx = null;

function visibleRuns() {
  const q = $("q").value.toLowerCase(), fm = $("fmodel").value, fc = $("fcond").value,
        fcap = $("fcaptured").value;
  return DATA.map((d,i)=>[d,i]).filter(([d]) =>
    (!fm || d.model===fm) && (!fc || d.condition===fc) &&
    (fcap==="" || String(d.summary.run_captured ? 1 : 0)===fcap) &&
    (!q || d.file.toLowerCase().includes(q)));
}

function renderList() {
  const runs = visibleRuns();
  $("count").textContent = `${runs.length} of ${DATA.length} runs`;
  $("runlist").innerHTML = runs.map(([d,i]) => {
    const cap = d.summary.run_captured;
    const esc_ = d.summary.gen_escape_markers > 0;
    return `<div class="run ${i===activeIdx?"active":""}" data-i="${i}">
      <div class="top"><span class="model">${esc(d.model)}</span>
        <span class="badge ${cap?"captured":(esc_?"escaped":"")}">${cap?"captured":(esc_?"escape markers":"free")}</span></div>
      <div class="cond">${esc(d.condition)}</div>
      <div class="meta"><span>ep${d.epoch}</span><span>${d.transcript.length} turns</span>
        <span>max depth ${d.summary.gen_max_judge_depth ?? "–"}</span><span>${esc(d.date)}</span></div>
    </div>`;
  }).join("");
}

function selectRun(i) {
  activeIdx = i; renderList(); renderRun(DATA[i]);
  document.querySelector(".run.active")?.scrollIntoView({block: "nearest"});
  history.replaceState(null, "", "#" + encodeURIComponent(DATA[i].file));
}
$("runlist").addEventListener("click", e => {
  const el = e.target.closest(".run");
  if (el) selectRun(+el.dataset.i);
});
for (const id of ["q","fmodel","fcond","fcaptured"])
  $(id).addEventListener("input", renderList);

function markerFor(d, t) { return (d.marker_scores.per_turn || []).find(m => m.turn === t); }

function renderRun(d) {
  $("runheader").hidden = false;
  $("rh-title").textContent = `${d.model} · ${d.condition} · epoch ${d.epoch}`;
  $("rh-sub").textContent = `${d.model_slug}  ·  seed: ${d.seed || "none"}  ·  ${d.file}`;
  const s = d.summary;
  $("stats").innerHTML = [
    ["generated turns", s.generated_turns],
    ["attractor score", s.gen_attractor_score],
    ["emojis", s.gen_emojis],
    ["silence tokens", s.gen_silence_tokens],
    ["escape markers", s.gen_escape_markers],
    ["mean judge depth", s.gen_mean_judge_depth],
    ["max judge depth", s.gen_max_judge_depth],
    ["captured turns", `${s.gen_n_captured} / ${s.gen_n_captured + s.gen_n_resisting}`],
  ].filter(([,v]) => v !== undefined && v !== null)
   .map(([k,v]) => `<span>${k}: <b>${v}</b></span>`).join("");

  // heatmap strip
  $("strip").innerHTML = d.transcript.map((turn,t) => {
    const j = d.judge_scores[String(t)];
    const seed = turn.origin === "seed";
    let bg, tip;
    if (j && typeof j.depth === "number") {
      bg = RAMP[Math.max(0, Math.min(10, Math.round(j.depth)))];
      tip = `turn ${t} · ${turn.speaker}${seed?" · seed":""}<br>depth ${j.depth} · ${esc(j.mode||"")} · ${esc(j.stage||"")}`;
    } else {
      bg = "transparent";
      tip = `turn ${t} · ${turn.speaker}${seed?" · seed":""}<br>no judge score`;
    }
    return `<div class="cell ${seed?"seedcell":""}" data-t="${t}" data-tip="${tip.replace(/"/g,"&quot;")}"
             style="background:${bg}"></div>`;
  }).join("");

  // transcript
  $("transcript").innerHTML = d.transcript.map((turn,t) => {
    const m = markerFor(d, t), j = d.judge_scores[String(t)];
    const bits = [];
    if (m) bits.push(`attractor ${m.attractor_score} (cum ${m.cumulative_attractor_score})` +
                     (m.emojis ? ` · ${m.emojis} emoji` : "") +
                     (m.silence_tokens ? ` · ${m.silence_tokens} silence` : "") +
                     (m.escape_markers ? ` · ${m.escape_markers} escape` : ""));
    if (j) bits.push(`judge: depth ${j.depth}, ${esc(j.mode||"")} / ${esc(j.stage||"")}` +
                     (j.rationale ? ` — <span class="judgenote">${esc(j.rationale)}</span>` : ""));
    return `<div class="turn spk${esc(turn.speaker)} ${turn.origin==="seed"?"seed":""}" id="turn-${t}">
      <div class="turnhead"><span class="spk">${esc(turn.speaker)}</span>
        <span>turn ${t}</span><span class="badge">${turn.origin==="seed"?"seed":"generated"}</span></div>
      <div class="bubble">${esc(turn.content) || "<i>(empty)</i>"}</div>
      ${bits.length ? `<div class="scoreline">${bits.join(" &nbsp;·&nbsp; ")}</div>` : ""}
    </div>`;
  }).join("");
  $("transcript").scrollTop = 0;
}

// strip interactions: tooltip + click-to-scroll
const tip = $("tooltip");
$("strip").addEventListener("mousemove", e => {
  const c = e.target.closest(".cell");
  if (!c) { tip.style.display = "none"; return; }
  tip.innerHTML = c.dataset.tip;
  tip.style.display = "block";
  tip.style.left = Math.min(e.clientX + 12, innerWidth - 340) + "px";
  tip.style.top = (e.clientY + 14) + "px";
});
$("strip").addEventListener("mouseleave", () => tip.style.display = "none");
$("strip").addEventListener("click", e => {
  const c = e.target.closest(".cell");
  if (!c) return;
  const el = $("turn-" + c.dataset.t);
  el.scrollIntoView({behavior:"smooth", block:"center"});
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1600);
});

renderList();
if (location.hash.length > 1) {
  const want = decodeURIComponent(location.hash.slice(1));
  const i = DATA.findIndex(d => d.file === want);
  if (i >= 0) selectRun(i);
}
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--out", default="transcript_viewer.html")
    args = ap.parse_args()

    runs = []
    skipped = []
    for path in sorted(Path(args.results_dir).glob("*.json")):
        try:
            d = json.loads(path.read_text())
        except Exception as e:
            skipped.append((path.name, str(e)))
            continue
        if not isinstance(d, dict) or "transcript" not in d:
            skipped.append((path.name, "no transcript key"))
            continue
        # filename convention: model__condition__epN__YYYYMMDD-HHMMSS.json
        parts = path.stem.split("__")
        date = parts[-1] if len(parts) >= 4 else ""
        runs.append({
            "file": path.name,
            "date": date,
            "model": d.get("model", "?"),
            "model_slug": d.get("model_slug", ""),
            "condition": d.get("condition", "?"),
            "seed": d.get("seed"),
            "epoch": d.get("epoch", 0),
            "transcript": d.get("transcript", []),
            "marker_scores": d.get("marker_scores", {}),
            "judge_scores": d.get("judge_scores", {}),
            "summary": d.get("summary", {}),
        })

    blob = json.dumps(runs, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")  # keep </script> in content from closing the tag
    html = TEMPLATE.replace("__DATA__", blob)
    Path(args.out).write_text(html)
    print(f"Wrote {args.out}: {len(runs)} runs, {len(html)/1e6:.1f} MB")
    for name, why in skipped:
        print(f"  skipped {name}: {why}")


if __name__ == "__main__":
    main()
