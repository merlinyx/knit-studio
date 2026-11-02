import unittest

from spacer_pipeline.engine import SpacerHelper


class EngineTests(unittest.TestCase):
    def test_spacer_engine_snapshot_imports(self) -> None:
        helper = SpacerHelper(width=12, front_carrier=1, back_carrier=2, filler_carrier=3)
        self.assertEqual(helper.width, 12)

    def test_short_row_filler_pairs_stop_before_tuck_pattern_repeats(self) -> None:
        pairs = SpacerHelper._short_row_filler_pairs
        self.assertEqual(pairs(4, 5, 3, 4), 1)   # two-stitch tip
        self.assertEqual(pairs(3, 6, 3, 4), 1)   # four-stitch tip
        self.assertEqual(pairs(1, 8, 3, 4), 2)   # four distinct phases
        self.assertEqual(pairs(1, 20, 3, 4), 2)  # phase repeats after 4 passes
        self.assertEqual(pairs(1, 20, 0, 4), 0)


if __name__ == "__main__":
    unittest.main()
