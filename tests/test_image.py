import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from spacer_pipeline.image import align_gradual_increase_rows, image_to_plan
from spacer_pipeline.model import row_from_runs


class ImageTests(unittest.TestCase):
    def test_odd_increase_interval_moves_later_event_before(self) -> None:
        rows = tuple(
            row_from_runs([run])
            for run in (
                (2, 5),
                (2, 5),
                (1, 6),  # increase at row 2
                (1, 6),
                (1, 6),
                (0, 7),  # increase at row 5 -> move to row 4
                (0, 7),
            )
        )
        adjusted, changes = align_gradual_increase_rows(rows)
        self.assertEqual(len(adjusted), len(rows))
        self.assertEqual(adjusted[4].to_list(), [[0, 7]])
        self.assertEqual(changes[0]["placement"], "before")
        self.assertEqual(changes[0]["to_row"], 4)

    def test_adjacent_increase_moves_later_event_after(self) -> None:
        rows = tuple(
            row_from_runs([run])
            for run in (
                (4, 5),
                (4, 5),
                (3, 6),  # increase at even row 2
                (2, 7),  # adjacent odd-row increase; next row repeats it
                (2, 7),
                (2, 7),
            )
        )
        adjusted, changes = align_gradual_increase_rows(rows)
        self.assertEqual(len(adjusted), len(rows))
        self.assertEqual(adjusted[3].to_list(), [[3, 6]])
        self.assertEqual(adjusted[4].to_list(), [[2, 7]])
        self.assertEqual(changes[0]["placement"], "after")
        self.assertEqual(changes[0]["to_row"], 4)

    def test_first_odd_increase_is_aligned_front_first(self) -> None:
        rows = tuple(
            row_from_runs([run])
            for run in (
                (3, 4),
                (3, 4),
                (3, 4),
                (2, 5),  # first increase is odd; move it to row 2
                (1, 6),
            )
        )
        adjusted, changes = align_gradual_increase_rows(rows)
        self.assertEqual(len(adjusted), len(rows))
        self.assertEqual(adjusted[2].to_list(), [[2, 5]])
        self.assertEqual(changes[0]["placement"], "before")
        self.assertEqual(changes[0]["to_row"], 2)

    def test_filled_silhouette_to_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shape.png"
            image = Image.new("L", (20, 20), 255)
            ImageDraw.Draw(image).rectangle((4, 2, 15, 17), fill=0)
            image.save(path)

            plan = image_to_plan(
                path,
                width_inches=2,
                height_inches=1,
                stitch_gauge=5,
                row_gauge=4,
            )
            self.assertEqual(len(plan.rows), 4)
            self.assertEqual(plan.grid_width, 10)
            self.assertTrue(all(row.to_list() == [[0, 9]] for row in plan.rows))

    def test_closed_outline_can_be_filled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outline.png"
            image = Image.new("L", (20, 20), 255)
            ImageDraw.Draw(image).rectangle((3, 3, 16, 16), outline=0, width=2)
            image.save(path)

            plan = image_to_plan(
                path,
                width_inches=2,
                height_inches=2,
                stitch_gauge=5,
                row_gauge=5,
                fill_outline=True,
            )
            self.assertEqual(len(plan.rows), 10)
            self.assertEqual(plan.grid_width, 10)
            self.assertTrue(all(len(row.runs) == 1 for row in plan.rows))


if __name__ == "__main__":
    unittest.main()
