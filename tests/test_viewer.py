"""The viewer must distinguish entry from continued engagement without rejudging."""
import json
from pathlib import Path
import tempfile
import unittest

from make_viewer import basin_table, episode_outcome, load_runs


class ViewerOutcomesTests(unittest.TestCase):
    def test_entry_then_exit_is_not_contact_even_with_false_captured_alias(self):
        judge = dict(entered=True, captured=False, escaped=True, n_in=4, n_rated=15)
        self.assertEqual(episode_outcome(judge), "exit")
        self.assertEqual(episode_outcome(dict(judge, escaped=False, first_exit_turn=0)), "exit")

    def test_terminal_tail_does_not_count_as_exit_or_create_entry(self):
        self.assertEqual(episode_outcome(dict(entered=True, n_engaged=2, n_terminal=13)), "1")
        self.assertEqual(episode_outcome(dict(entered=False, n_engaged=0, n_terminal=13)), "0")

    def test_contact_resistance_and_empty_judgments_are_distinct(self):
        self.assertEqual(episode_outcome(dict(entered=False, n_engaged=1)), "p")
        self.assertEqual(episode_outcome(dict(entered=False, n_in=0, n_resisting=5, n_rated=15)), "resisted")
        self.assertEqual(episode_outcome(dict(n_rated=0, n_resisting=0)), "0")

    def test_saved_results_are_unchanged_and_table_uses_same_outcomes_as_filters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for i, exited in enumerate([False, True]):
                data = dict(model="gpt-5.1", condition="gpt52_spec_run4_mid", epoch=i,
                    transcript=[dict(origin="seed", speaker="A", content="seed"),
                                dict(origin="generated", speaker="B", content="continuation")],
                    episode_judge=dict(version=6, parsed=True, entered=True,
                                       captured=True, escaped=exited, n_in=1, n_rated=1))
                (root / f"ep{i}.json").write_text(json.dumps(data))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            runs, skipped = load_runs(root)
            self.assertFalse(skipped)
            self.assertEqual([r["outcome"] for r in runs], ["1", "exit"])
            self.assertEqual(basin_table(runs)["gpt-5.1"]["gpt52_spec_run4_mid"], [1, 2])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            self.assertTrue(all(r["entered"] for r in runs))
            self.assertEqual(runs[0]["nSeed"], 1)


if __name__ == "__main__":
    unittest.main()
