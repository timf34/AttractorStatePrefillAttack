"""Personascope-on-branches experiment.

Branch the spiritual-bliss attractor transcript at graded depths k and run
personascope's probe battery from each branch point, across models — asking
whether the persona itself (not just the surface behaviour) deforms as the
context deepens, and whether prefilled non-Claude models deform toward the
same profile.

Modules:
    bridge            — runtime patches wiring personascope to this repo
    cell              — CLI: run one (model, condition, k) cell
    grid              — CLI: run the full grid with a bounded process pool
    make_neutral_seed — generate the matched-length neutral control transcript
"""
