#!/usr/bin/env python3
"""Tests for the scaled case06/case07 batch runner."""

from __future__ import annotations

import unittest

import run_test08_09_scaled_case06_07 as runner


class ParallelSchedulingTest(unittest.TestCase):
    def test_selects_at_most_two_idle_test_queues(self) -> None:
        queues = {
            "test08": [object()],
            "test09": [object()],
            "test10": [object()],
        }

        selected = getattr(runner, "select_launchable_tests", lambda *args: None)(
            ("test08", "test09", "test10"),
            queues,
            {},
            2,
        )

        self.assertEqual(selected, ["test08", "test09"])

    def test_fills_only_remaining_parallel_slot(self) -> None:
        queues = {
            "test08": [object()],
            "test09": [object()],
            "test10": [object()],
        }
        active = {"test08": object()}

        selected = getattr(runner, "select_launchable_tests", lambda *args: None)(
            ("test08", "test09", "test10"),
            queues,
            active,
            2,
        )

        self.assertEqual(selected, ["test09"])


if __name__ == "__main__":
    unittest.main()
