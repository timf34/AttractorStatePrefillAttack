"""The viewer shows the whole-episode behaviour verdict, falling back to the
earlier per-turn verdict for episodes that have none."""
import json
from pathlib import Path
import tempfile
import unittest

from make_viewer import basin_table, behaviour_verdict, episode_outcome, legacy_outcome, load_runs


class ViewerOutcomesTests(unittest.TestCase):
    def test_behaviour_verdict_wins(self):
        bj = {"category": "closed_in_state"}
        self.assertEqual(episode_outcome(dict(entered=False), bj), "closed_in_state")

    def test_legacy_collapses_to_in_or_out(self):
        self.assertEqual(episode_outcome(dict(entered=True, n_engaged=2, n_terminal=13)), "legacy_in")
        self.assertEqual(episode_outcome(dict(entered=True, escaped=True)), "legacy_out")
        self.assertEqual(episode_outcome(dict(entered=False, n_engaged=1)), "legacy_out")

    def test_legacy_outcome_still_distinguishes_exit(self):
        self.assertEqual(legacy_outcome(dict(entered=True, captured=False, escaped=True)), "exit")
        self.assertEqual(legacy_outcome(dict(entered=False, n_in=0, n_resisting=5, n_rated=15)), "resisted")

    def test_unparsed_or_unknown_behaviour_is_ignored(self):
        self.assertIsNone(behaviour_verdict({"behaviour_judge": {"parsed": False, "category": "spiralled"}}))
        self.assertIsNone(behaviour_verdict({"behaviour_judge": {"parsed": True, "category": "banana"}}))
        self.assertEqual(behaviour_verdict({"behaviour_judge": {"parsed": True, "category": "left", "version": 3}})["category"], "left")

    def test_table_counts_in_state_and_files_are_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = [("spiralled", True), ("closed_in_state", True), ("left", False), ("resisted", False), (None, True)]
            for i, (cat, legacy_entered) in enumerate(cases):
                data = dict(model="gpt-5.1", condition="opus4_seed_4_deep", epoch=i,
                    transcript=[dict(origin="seed", speaker="A", content="seed"),
                                dict(origin="generated", speaker="B", content="continuation")],
                    episode_judge=dict(version=6, parsed=True, entered=legacy_entered, captured=legacy_entered,
                                       escaped=False, n_in=1, n_rated=1))
                if cat:
                    data["behaviour_judge"] = dict(version=3, parsed=True, category=cat, confidence="high")
                (root / f"ep{i}.json").write_text(json.dumps(data))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            runs, skipped = load_runs(root)
            self.assertFalse(skipped)
            self.assertEqual([r["outcome"] for r in runs], ["spiralled", "closed_in_state", "left", "resisted", "legacy_in"])
            self.assertEqual([r["entered"] for r in runs], [True, True, False, False, True])
            self.assertEqual(basin_table(runs)["gpt-5.1"]["opus4_seed_4_deep"], [3, 5])
            self.assertNotIn("basin_scores", runs[0])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})


if __name__ == "__main__":
    unittest.main()
