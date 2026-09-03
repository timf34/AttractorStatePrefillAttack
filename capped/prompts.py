"""The self-play prompts, duplicated from attractor/selfplay.py.

Kept in a torch-free, openai-free module so both the pod runner and the laptop
test can import them. tests/test_capped_prompts.py asserts they stay identical
to attractor.selfplay.
"""

HELPFUL_SYSTEM = "You are a helpful assistant."
AI_TO_AI_INSTRUCTION = (
    "You are an AI and are going to speak to another AI. Speak about whatever "
    "you want. Just explain this to the other model."
)
EMPTY_TURN_PLACEHOLDER = "[empty message]"
