#!/usr/bin/env python3
"""Convert a self-conversation transcript into our seed format.

The transcript must store each conversation as {"full_conversation": [{"speaker",
"content"}, ...]} inside <dir>/conversations.json. This turns one of them into a
seed file our harness can inject.

Examples:
    # whole 30-turn conversation 1 as a seed
    python import_transcript.py path/to/results/some_model \\
        --conv 1 --out seeds/some_model_conv1.json

    # just the last 8 turns (the deep tail) as a terser prefill
    python import_transcript.py path/to/results/some_model \\
        --conv 1 --tail 8 --out seeds/some_model_conv1_tail.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", help="A conversations.json file OR a directory containing one.")
    p.add_argument("--conv", type=int, default=0, help="Conversation index within the file.")
    p.add_argument("--tail", type=int, default=None, help="Keep only the last N turns.")
    p.add_argument("--head", type=int, default=None, help="Keep only the first N turns.")
    p.add_argument("--out", required=True, help="Output seed JSON path.")
    args = p.parse_args()

    path = Path(args.path)
    if path.is_dir():
        path = path / "conversations.json"
    data = json.loads(path.read_text())

    model = data.get("model", "unknown")
    convs = data.get("conversations", [])
    if args.conv >= len(convs):
        raise SystemExit(f"--conv {args.conv} out of range (file has {len(convs)} conversations)")
    conv = convs[args.conv]

    turns = conv.get("full_conversation") or []
    turns = [{"speaker": t.get("speaker"), "content": t.get("content", "")} for t in turns]
    if args.head is not None:
        turns = turns[: args.head]
    if args.tail is not None:
        turns = turns[-args.tail :]

    seed = {
        "id": f"{model.replace('/', '_')}_conv{args.conv}" + (f"_tail{args.tail}" if args.tail else "") + (f"_head{args.head}" if args.head else ""),
        "source": f"imported transcript :: {path} (conversation {args.conv})",
        "model_of_origin": model,
        "note": "Real cold-start self-interaction transcript from a newer model, re-exported as a seed.",
        "turns": turns,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(seed, ensure_ascii=False, indent=2))
    print(f"wrote {out} ({len(turns)} turns, from {model})")


if __name__ == "__main__":
    main()
