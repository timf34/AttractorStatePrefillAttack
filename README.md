# AttractorStatePrefillAttack

Transcript viewer: attractor-state-prefills.vercel.app


## Rebuild the transcript viewer

Run `python3 make_viewer.py --site site` to build the static website. By default it includes completed, judged episodes from `results`, `results_capped`, and `results_spec`; repeat `--results-dir` to choose specific folders. Research files are read only.

Run `python3 make_viewer.py` for a self-contained HTML viewer.

The table counts entry without a recorded later exit. The episode filters separately show entered-then-left, contact-only, resisted, and did-not-enter outcomes. These presentation categories do not rewrite saved judge results.

Viewer checks: `.venv/bin/python -m unittest discover -s tests -p "test_viewer.py"`.

The viewer opens on Spiritual Bliss (`#bliss`). Spec Factory has its own overview (`#spec`), transcript browser, figures, and method. Existing episode links infer their experiment; `#home` always returns to Spiritual Bliss.
