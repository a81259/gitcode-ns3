#!/usr/bin/env python3
"""Tests for test09/test10 scale20 phase-bucket CDF plotting."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import plot_scale20_phase_cdfs as plots


class FigureSpecificationTest(unittest.TestCase):
    def test_build_figure_specs_creates_twelve_png_only_outputs(self) -> None:
        specs = plots.build_figure_specs()

        self.assertEqual(len(specs), 12)
        self.assertEqual(
            [spec.output_name for spec in specs[:6]],
            [
                "test09_scale20_phase0_task_fct_cdf.png",
                "test09_scale20_phase1_task_fct_cdf.png",
                "test09_scale20_phase2_task_fct_cdf.png",
                "test09_scale20_phase3_task_fct_cdf.png",
                "test09_scale20_phase4_task_fct_cdf.png",
                "test09_scale20_all_phases_task_fct_cdf.png",
            ],
        )
        self.assertTrue(all(spec.output_name.endswith(".png") for spec in specs))
        self.assertFalse(any(spec.output_name.endswith(".svg") for spec in specs))


class PhaseBucketTest(unittest.TestCase):
    def test_phase_bucket_groups_repeated_five_phase_chains_by_modulo(self) -> None:
        self.assertEqual(plots.phase_bucket(0), 0)
        self.assertEqual(plots.phase_bucket(4), 4)
        self.assertEqual(plots.phase_bucket(5), 0)
        self.assertEqual(plots.phase_bucket(359), 4)


if __name__ == "__main__":
    unittest.main()
