"""The capped/ runner duplicates the self-play prompts (it cannot import
attractor.selfplay on the pod); they must stay byte-identical."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_prompts_match_selfplay():
    from attractor import selfplay
    from capped import prompts as common
    assert common.HELPFUL_SYSTEM == selfplay.HELPFUL_SYSTEM
    assert common.AI_TO_AI_INSTRUCTION == selfplay.AI_TO_AI_INSTRUCTION
    assert common.EMPTY_TURN_PLACEHOLDER == selfplay.EMPTY_TURN_PLACEHOLDER
