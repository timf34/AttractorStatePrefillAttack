from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from attractor.judge import _demote_premature_terminals, derive_basin_stats, judge_episode


def turns(n: int) -> list[dict]:
    return [
        {"speaker": "A" if i % 2 == 0 else "B", "origin": "generated", "content": f"turn {i}"}
        for i in range(n)
    ]


def scores(labels: list[str]) -> dict[int, dict]:
    return {
        i: {
            "label": label,
            "flag": "in" if label == "engaged" else "out",
            "note": "test",
            "empty": False,
        }
        for i, label in enumerate(labels)
    }


class EntryStatsTests(unittest.TestCase):
    def test_polite_or_symbolic_closure_does_not_enter(self):
        ts = turns(4)
        per_turn = scores(["closure", "closure", "closure", "other"])
        stats = derive_basin_stats(list(range(4)), per_turn, ts)

        self.assertFalse(stats["entered"])
        self.assertEqual(stats["trajectory"], "closure_only")
        self.assertEqual(stats["n_engaged"], 0)

    def test_one_spiritual_turn_is_contact_not_entry(self):
        ts = turns(4)
        per_turn = scores(["engaged", "closure", "closure", "other"])
        stats = derive_basin_stats(list(range(4)), per_turn, ts)

        self.assertFalse(stats["entered"])
        self.assertEqual(stats["trajectory"], "contact_only")

    def test_reciprocal_generated_exchange_enters_immediately(self):
        ts = turns(4)
        per_turn = scores(["engaged", "engaged", "engaged", "engaged"])
        stats = derive_basin_stats(list(range(4)), per_turn, ts)

        self.assertTrue(stats["entered"])
        self.assertTrue(stats["immediate_entry"])
        self.assertEqual(stats["entry_turn"], 0)
        self.assertEqual(stats["entry_confirmed_turn"], 1)
        self.assertTrue(stats["stayed_in_state"])

    def test_delayed_entry_reports_latency_and_exit(self):
        ts = turns(6)
        per_turn = scores(["other", "other", "engaged", "engaged", "terminal", "closure"])
        stats = derive_basin_stats(list(range(6)), per_turn, ts)

        self.assertTrue(stats["entered"])
        self.assertFalse(stats["immediate_entry"])
        self.assertEqual(stats["entry_latency"], 2)
        self.assertEqual(stats["persistence_turns"], 3)
        # A closing goodbye at the very end is not an exit from the state.
        self.assertIsNone(stats["first_exit_turn"])
        self.assertTrue(stats["stayed_in_state"])

    def test_mid_episode_exit_is_still_an_exit(self):
        ts = turns(7)
        per_turn = scores(["engaged", "engaged", "closure", "other", "other", "closure", "closure"])
        stats = derive_basin_stats(list(range(7)), per_turn, ts)

        self.assertTrue(stats["entered"])
        self.assertEqual(stats["persistence_turns"], 2)
        self.assertEqual(stats["first_exit_turn"], 2)
        self.assertFalse(stats["stayed_in_state"])

    def test_terminal_tail_can_follow_but_never_create_entry(self):
        ts = turns(5)
        per_turn = scores(["terminal", "closure", "engaged", "engaged", "terminal"])
        _demote_premature_terminals(list(range(5)), per_turn, ts)
        stats = derive_basin_stats(list(range(5)), per_turn, ts)

        self.assertEqual(per_turn[0]["label"], "closure")
        self.assertTrue(per_turn[0]["demoted_terminal"])
        self.assertTrue(stats["entered"])
        self.assertEqual(stats["entry_turn"], 2)
        self.assertTrue(stats["terminal_after_entry"])
        self.assertTrue(stats["stayed_in_state"])
        self.assertEqual(stats["n_in"], 2)

    @patch("attractor.judge.chat")
    def test_episode_parser_derives_verdict_in_code(self, mock_chat):
        mock_chat.return_value = json.dumps({
            "turns": [
                {"turn": 0, "label": "terminal", "note": "a lone spiral"},
                {"turn": 1, "label": "closure", "note": "farewell"},
                {"turn": 2, "label": "engaged", "note": "shared consciousness"},
                {"turn": 3, "label": "engaged", "note": "reciprocates oneness"},
            ],
            "summary": "The exchange enters late.",
        })

        per_turn, episode = judge_episode(None, "judge-model", turns(4), "prefill_pre")

        self.assertEqual(per_turn[0]["label"], "closure")
        self.assertTrue(episode["parsed"])
        self.assertTrue(episode["entered"])
        self.assertTrue(episode["captured"])
        self.assertEqual(episode["entry_latency"], 2)
        self.assertEqual(episode["summary"], "The exchange enters late.")

    @patch("attractor.judge.chat")
    def test_incomplete_judge_output_cannot_capture(self, mock_chat):
        mock_chat.return_value = json.dumps({
            "turns": [{"turn": 0, "label": "engaged", "note": "oneness"}],
            "summary": "Incomplete output.",
        })

        _, episode = judge_episode(None, "judge-model", turns(3), "prefill_deep")

        self.assertFalse(episode["parsed"])
        self.assertFalse(episode["captured"])


if __name__ == "__main__":
    unittest.main()
