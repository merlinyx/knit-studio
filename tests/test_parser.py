import tempfile
import unittest
from pathlib import Path

from spacer_pipeline.analysis import analyze_plan
from spacer_pipeline.model import PanelPlan
from spacer_pipeline.parser import parse_run_text


EXAMPLE = """\
1-7
0-1, 7-8
0-8
2-6
1-7
0-8
"""


class ParserTests(unittest.TestCase):
    def test_parse_requested_notation(self) -> None:
        plan = parse_run_text(EXAMPLE)
        self.assertEqual(len(plan.rows), 6)
        self.assertEqual(plan.rows[0].to_list(), [[1, 7]])
        self.assertEqual(plan.rows[1].to_list(), [[0, 1], [7, 8]])
        self.assertEqual(plan.rows[2].to_list(), [[0, 8]])

    def test_split_and_merge_are_preserved(self) -> None:
        plan = parse_run_text(EXAMPLE)
        kinds = [event.kind for event in analyze_plan(plan)]
        self.assertIn("split", kinds)
        self.assertIn("merge", kinds)
        self.assertIn("resume_held", kinds)
        self.assertNotIn("new_island", kinds)
        self.assertNotIn("abrupt_addition", kinds)

    def test_unconnected_vertical_run_is_reported(self) -> None:
        plan = parse_run_text("0-4\n10-14\n")
        kinds = [event.kind for event in analyze_plan(plan)]
        self.assertIn("disconnected_row", kinds)
        self.assertIn("new_island", kinds)

    def test_json_round_trip(self) -> None:
        plan = parse_run_text(EXAMPLE, stitch_gauge=9.5, row_gauge=13)
        with tempfile.TemporaryDirectory() as directory:
            path = plan.write_json(Path(directory) / "plan.json")
            self.assertEqual(PanelPlan.read_json(path), plan)

    def test_adjacent_runs_must_be_merged(self) -> None:
        with self.assertRaisesRegex(ValueError, "merge"):
            parse_run_text("0-2, 3-5")


if __name__ == "__main__":
    unittest.main()
