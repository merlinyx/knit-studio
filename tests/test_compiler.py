import tempfile
import unittest
from pathlib import Path

from spacer_pipeline.compiler import CompileConfig, compile_panel_plan
from spacer_pipeline.parser import parse_run_text


class CompilerTests(unittest.TestCase):
    def assert_carrier_motion_is_monotonic_after(
        self, output: str, marker: str, carriers: set[str]
    ) -> None:
        """Check that operation directions agree with carrier movement."""
        positions: dict[str, int] = {}
        checking = False
        for line in output.splitlines():
            if marker in line:
                checking = True
            words = line.split()
            if len(words) < 4 or words[0] not in {"knit", "tuck", "miss"}:
                continue
            direction, location = words[1:3]
            needle = int(location[1:])
            for carrier in set(words[3:]) & carriers:
                previous = positions.get(carrier)
                if checking and previous is not None:
                    if direction == "+":
                        self.assertGreaterEqual(
                            needle, previous, f"backward carrier move: {line}"
                        )
                    else:
                        self.assertLessEqual(
                            needle, previous, f"backward carrier move: {line}"
                        )
                positions[carrier] = needle

    def test_single_run_plan_compiles_with_gradual_and_step_changes(self) -> None:
        plan = parse_run_text("2-13\n1-14\n1-14\n4-11\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "panel.k")
            output = result.output_path.read_text()
        self.assertEqual(result.ordinary_blocks, 4)
        self.assertEqual(result.step_changes, 1)
        self.assertIn("panel compiler: abrupt range", output)
        self.assertIn(";!knitout-2", output)

    def test_abrupt_expansion_merges_cast_on_with_face_rows(self) -> None:
        plan = parse_run_text("5-14\n1-18\n1-18\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "expansion.k")
            output = result.output_path.read_text()
        self.assertEqual(result.step_changes, 1)
        self.assertIn("prepare merged abrupt expansion 5-14 -> 1-18", output)
        self.assertIn(
            "complete merged abrupt-expansion cast-on in the first "
            "directional face transition",
            output,
        )
        # The filler is secured beyond the expanded right edge with a real
        # temporary tuck, not merely repositioned with a miss.
        self.assertIn(
            "secure filler beyond transition right edge with temporary tuck",
            output,
        )
        self.assertIn("tuck + f39 7", output)

        # Preserve the carrier's natural next direction.  The first face
        # pass goes left through the old center and seeds the new left edge.
        merged = output.split("complete merged abrupt-expansion", 1)[1]
        self.assertIn("knit - f27 2 4", merged)
        self.assertIn(
            "tuck - f7 2 4\nmiss - f5 2 4\n"
            "tuck - f3 2 4\nmiss - f1 2 4",
            merged,
        )
        # The return pass completes the left cast-on, crosses the old fabric,
        # and seeds the new right edge; the third pass completes that edge.
        self.assertIn("tuck + f1 2 4\nknit + f3 2 4", merged)
        self.assertIn("tuck + f29 2 4\nmiss + f31 2 4", merged)
        self.assertIn("tuck - f35 2 4\nknit - f33 2 4", merged)
        # The old standalone cast-on emitted two separate parity passes.
        self.assertNotIn("miss - f27 2 4\nmiss - f25 2 4", output)
        # Once a real filler pass anchors the yarn inside the fabric, its
        # temporary parking tuck is redundantly dropped for reliability.
        self.assertIn("drop temporary filler parking tuck", output)
        self.assertEqual(output.count("drop f39\n"), 2)
        self.assertIn(
            "add one filler transition pass to follow the expanded face "
            "carriers",
            output,
        )
        self.assertNotIn("omit trailing filler before abrupt cast-off", output)

    def test_abrupt_cast_off_ends_outgoing_width_on_face_rows(self) -> None:
        plan = parse_run_text("1-20\n1-20\n6-15\n6-15\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "shrink.k")
            output = result.output_path.read_text()

        marker = (
            ";panel compiler: omit trailing filler before abrupt cast-off "
            "1-20 -> 6-15; end outgoing width on face rows"
        )
        self.assertIn(marker, output)
        transition = output.split(marker, 1)[1].split(
            ";panel compiler: abrupt range 1-20 -> 6-15", 1
        )[0]
        self.assertIn("0 filler pair(s)", transition)
        self.assertFalse(
            any(
                line.startswith(("tuck + ", "tuck - "))
                and line.endswith(" 7")
                for line in transition.splitlines()
            )
        )
        self.assertTrue(transition.strip().splitlines()[-1].startswith("knit "))
        self.assertIn("cast off 10 outgoing stitches", output)

    def test_gradual_increase_uses_direction_consistent_edge_tucks(self) -> None:
        plan = parse_run_text("2-13\n1-14\n1-14\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "increase.k")
            output = result.output_path.read_text()

        # Both newly introduced front edge needles are tucked during the
        # outgoing leftward pass and knitted during the rightward return.
        self.assertIn("tuck - f27 2 4", output)
        self.assertIn("tuck - f1 2 4\nknit + f1 2 4", output)
        self.assertNotIn("miss - f1 2 4\ntuck + f1 2 4", output)
        self.assertNotIn("miss - f27 2 4\ntuck + f27 2 4", output)

    def test_cast_off_returns_to_new_edge_before_dropping_shoulders(self) -> None:
        plan = parse_run_text("1-20\n6-15\n6-15\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "shrink.k")
            output = result.output_path.read_text()

        transition_marker = (
            ";cast-off transition pass: cross surviving front range and "
            "park beside its next edge before dropping waste"
        )
        self.assertIn(transition_marker, output)
        transition = output.split(transition_marker, 1)[1].split(
            ";drop cast-off waste from the step change", 1
        )[0]
        transition_knits = [
            line for line in transition.splitlines() if line.startswith("knit ")
        ]
        # The carrier returns from the old right edge, crosses the surviving
        # front face, and stops on the nearest left-shoulder waste needle.
        self.assertEqual(transition_knits[0], "knit - f40 2 4")
        self.assertEqual(transition_knits[-1], "knit - f10 2 4")
        self.assertNotIn("knit - f9 2 4", transition_knits)

        after_drop = output.split(
            ";drop cast-off waste from the step change", 1
        )[1]
        next_front_operation = next(
            line for line in after_drop.splitlines() if line.endswith(" 2 4")
        )
        self.assertEqual(next_front_operation, "knit + f11 2 4")

    def test_cast_off_entry_preserves_left_side_start(self) -> None:
        # The merged abrupt expansion flips the face carriers, leaving the
        # front set on the left with its next pass travelling right. A later
        # shrink must not fake-reposition it across the whole panel.
        plan = parse_run_text("5-14\n1-18\n1-18\n6-13\n6-13\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "direction.k")
            output = result.output_path.read_text()

        shrink = output.split(
            ";panel compiler: abrupt range 1-18 -> 6-13", 1
        )[1]
        self.assertIn(
            "cast-off entry: preserve next + front direction; "
            "park just beyond left transition edge",
            shrink,
        )
        self.assertIn("miss - f0 2 4", shrink)
        self.assertNotIn("miss + f37 2 4", shrink)
        first_front_knit = next(
            line for line in shrink.splitlines() if line.endswith(" 2 4")
            and line.startswith("knit ")
        )
        self.assertEqual(first_front_knit, "knit + f1 2 4")

    def test_one_sided_cast_off_parks_on_actual_carrier_side(self) -> None:
        # Only the left edge is removed while the front carrier is on the
        # right. Parking relative to the waste would send f39 backward to f9.
        marker = ";panel compiler: abrupt range 1-20 -> 5-20"
        plan = parse_run_text("1-20\n5-20\n5-20\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "left-shrink.k")
            output = result.output_path.read_text()

        shrink = output.split(marker, 1)[1]
        self.assertIn("miss + f41 2 4", shrink)
        self.assertNotIn("miss + f9 2 4", shrink)
        self.assertIn("knit - f39 2 4", shrink)
        self.assert_carrier_motion_is_monotonic_after(
            output, marker, {"2", "4"}
        )

    def test_one_sided_cast_off_is_mirrored_for_rightward_flow(self) -> None:
        # The initial expansion leaves the face carriers on the left. A later
        # right-only shrink must remain there instead of parking by right waste.
        marker = ";panel compiler: abrupt range 1-18 -> 1-14"
        plan = parse_run_text("5-14\n1-18\n1-18\n1-14\n1-14\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "right-shrink.k")
            output = result.output_path.read_text()

        shrink = output.split(marker, 1)[1]
        self.assertIn("miss - f0 2 4", shrink)
        self.assertNotIn("miss - f28 2 4", shrink)
        self.assertIn("knit + f1 2 4", shrink)
        self.assert_carrier_motion_is_monotonic_after(
            output, marker, {"2", "4"}
        )

    def test_cast_off_parking_includes_just_vacated_gradual_edge(self) -> None:
        # A gradual decrease changes min_n after the face pass, but the
        # carrier itself remains one needle farther left until it moves again.
        marker = ";panel compiler: abrupt range 2-17 -> 5-14"
        plan = parse_run_text("5-14\n1-18\n2-17\n5-14\n5-14\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "vacated-edge.k")
            output = result.output_path.read_text()

        shrink = output.split(marker, 1)[1]
        self.assertIn("miss - f0 2 4", shrink)
        self.assertNotIn("miss - f2 2 4", shrink)
        self.assert_carrier_motion_is_monotonic_after(
            output, marker, {"2", "4"}
        )

    def test_mixed_abrupt_shift_parks_all_carriers_outside_union(self) -> None:
        marker = ";panel compiler: abrupt range 1-20 -> 5-24"
        plan = parse_run_text("1-20\n5-24\n5-24\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "shift.k")
            output = result.output_path.read_text()

        shifted = output.split(marker, 1)[1]
        self.assertIn("miss + f49 2 4", shifted)
        self.assertIn("miss + f49 8 10", shifted)
        self.assertIn("tuck + f51 7", shifted)
        self.assertIn("tuck - f47 2 4", shifted)
        self.assertIn("tuck - b48 8 10", shifted)
        self.assert_carrier_motion_is_monotonic_after(
            output, marker, {"2", "4", "7", "8", "10"}
        )

    def test_finish_uses_existing_left_side_filler_direction(self) -> None:
        # A three-pass abrupt expansion plus its filler transition leaves the
        # filler on the left, ready to travel right into the merged waste.
        plan = parse_run_text("5-14\n1-18\n1-18\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "finish.k")
            output = result.output_path.read_text()

        finish = output.split(";finish stage 3: 6 merged rows, drop", 1)[1]
        operations = [
            line for line in finish.splitlines()
            if line.startswith(("knit ", "tuck ", "miss "))
        ]
        self.assertEqual(operations[0], "knit + f1 7")
        self.assertNotIn("miss + f37 7", finish)

    def test_consecutive_steps_finish_pending_cast_off_rows(self) -> None:
        plan = parse_run_text("1-20\n3-18\n6-15\n6-15\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "steps.k")
            output = result.output_path.read_text()

        second_step = output.split(
            ";panel compiler: abrupt range 3-18 -> 6-15", 1
        )[1]
        finish_pending = second_step.index(
            ";complete 2 pending cast-off front row(s) before the next "
            "width transition"
        )
        transition = second_step.index(";cast-off transition pass:")
        drop = second_step.index(";drop cast-off waste from the step change")
        new_step = second_step.index(";=== step width 16 -> 10")
        self.assertLess(finish_pending, transition)
        self.assertLess(transition, drop)
        self.assertLess(drop, new_step)

    def test_expansion_keeps_carriers_aligned_for_later_short_rows(self) -> None:
        plan = parse_run_text(
            "5-14\n"
            "1-18\n"
            "3-6, 13-16\n"
            "4-5, 14-15\n"
            "1-18\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(
                plan, Path(directory) / "expansion-short-rows.k"
            )
            output = result.output_path.read_text()
        self.assertEqual(result.step_changes, 1)
        self.assertEqual(result.short_row_groups, 1)
        self.assertIn("short-row spacer block", output)

    def test_two_nested_triangles_compile_as_short_rows(self) -> None:
        plan = parse_run_text(
            "1-20\n"
            "3-6, 15-18\n"
            "4-5, 16-17\n"
            "1-20\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "triangles.k")
            output = result.output_path.read_text()
        self.assertEqual(result.ordinary_blocks, 2)
        self.assertEqual(result.short_row_groups, 1)
        self.assertEqual(result.short_row_levels, 2)
        self.assertIn("short-row spacer block: lobe 1, level 0, run 15-18", output)
        self.assertIn("short-row spacer block: lobe 0, level 0, run 3-6", output)
        self.assertLess(output.index("run 15-18"), output.index("run 3-6"))
        self.assertIn("knit - f39 2 4", output)

    def test_multi_runs_can_be_rejected(self) -> None:
        plan = parse_run_text("1-20\n3-6, 15-18\n")
        config = CompileConfig(multi_run_policy="error")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "enable the short-rows policy"):
                compile_panel_plan(plan, Path(directory) / "panel.k", config)

    def test_short_rows_must_remain_inside_connected_base(self) -> None:
        plan = parse_run_text("2-19\n1-4, 17-20\n")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "outside connected base"):
                compile_panel_plan(plan, Path(directory) / "panel.k")

    def test_continuing_center_is_ordinary_and_side_bumps_are_short_rows(self) -> None:
        plan = parse_run_text(
            "1-38\n"
            "1-8, 15-24, 31-38\n"
            "2-7, 15-24, 32-37\n"
            "4-5, 15-24, 34-35\n"
            "15-24\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "bumps.k")
            output = result.output_path.read_text()
        self.assertEqual(result.ordinary_blocks, 5)
        self.assertEqual(result.short_row_groups, 1)
        self.assertEqual(result.short_row_levels, 3)
        self.assertIn("inferred anonymous continuing component", output)
        self.assertIn("15-24, 15-24, 15-24", output)
        self.assertNotIn("short-row spacer block: lobe 1, level 0, run 15-24", output)
        self.assertIn(
            "drop terminal short-row loops without finish treatment", output
        )
        # Logical needles 1..14 and 25..38 leave the active range. Both
        # half-gauge face loops must be released before the center grows.
        self.assertIn("drop f1", output)
        self.assertIn("drop b2", output)
        self.assertIn("drop f75", output)
        self.assertIn("drop b76", output)
        self.assertEqual(output.count("drop f1\n"), 2)
        self.assertEqual(output.count("drop b2\n"), 2)
        self.assertEqual(output.count("drop f75\n"), 2)
        self.assertEqual(output.count("drop b76\n"), 2)
        self.assertRegex(
            output,
            r"pruned [1-9][0-9]* unresolved filler tuck\(s\) before shape drop",
        )
        self.assertNotIn("cast off 28 outgoing stitches", output)

    def test_narrow_short_row_tip_adapts_filler_spacing(self) -> None:
        plan = parse_run_text(
            "1-20\n"
            "3-6, 15-18\n"
            "4-5, 16-17\n"
            "1-20\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "narrow.k")
            output = result.output_path.read_text()
        self.assertIn("width 2 cannot fit spacing 4; using 1 with offset >= 1", output)
        self.assertIn(
            "use 1 of 3 requested pair(s) at width 2 to avoid repeated tuck needles",
            output,
        )
        final_tip = output.split(
            ";short-row spacer block: lobe 0, level 1, run 4-5", 1
        )[1].split(";spacer block:", 1)[0]
        filler_tucks = [
            line.split()[2]
            for line in final_tip.splitlines()
            if line.startswith("tuck ") and line.endswith(" 7")
        ]
        self.assertEqual(len(filler_tucks), len(set(filler_tucks)))

    def test_gradual_decrease_repeats_drops_on_vacated_edge_needles(self) -> None:
        plan = parse_run_text("1-10\n2-9\n")
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(plan, Path(directory) / "decrease.k")
            output = result.output_path.read_text()
        self.assertIn("repeat drop vacated decrease needle 1 x2", output)
        self.assertIn("repeat drop vacated decrease needle 10 x2", output)
        self.assertEqual(output.count("drop f1\n"), 2)
        self.assertEqual(output.count("drop b2\n"), 2)
        self.assertEqual(output.count("drop f19\n"), 2)
        self.assertEqual(output.count("drop b20\n"), 2)

    def test_drop_repeat_count_is_configurable(self) -> None:
        plan = parse_run_text("1-10\n2-9\n")
        config = CompileConfig(drop_repeats=3)
        with tempfile.TemporaryDirectory() as directory:
            result = compile_panel_plan(
                plan, Path(directory) / "decrease-three-drops.k", config
            )
            output = result.output_path.read_text()
        self.assertIn("repeat drop vacated decrease needle 1 x3", output)
        self.assertEqual(output.count("drop f1\n"), 3)
        self.assertEqual(output.count("drop b2\n"), 3)


if __name__ == "__main__":
    unittest.main()
