"""Activation-capping arm of the bliss-prefill experiment (runs on a GPU pod).

Same two-instance self-play loop as ``attractor/selfplay.py`` and the same
prefill seeds, but the model runs locally through transformers so that its
residual stream can be capped along the Assistant Axis (Lu et al. 2026)
while it generates. See capped/README.md.
"""
