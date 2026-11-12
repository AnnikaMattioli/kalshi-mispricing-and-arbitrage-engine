from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kalshi_engine.dashboard import latest_sweeps

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


def capture(directory, ended, *, failed=False, incomplete=False):
    path = directory / f"{ended:%Y%m%dT%H%M%SZ}-KXHIGHNY-1234abcd.jsonl"
    rows = [{"kind": "sweep_start", "series": "KXHIGHNY"}]
    if not incomplete:
        rows.append({"kind": "sweep_end", "ended_at": ended.isoformat(), "counts": {
            "markets_discovered": 1, "books_received": int(not failed),
            "request_failures": int(failed),
        }})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


class DashboardTests(unittest.TestCase):
    def test_latest_sweep_is_selected_and_ages(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            capture(folder, NOW - timedelta(minutes=10))
            latest = capture(folder, NOW - timedelta(seconds=10))
            report, = latest_sweeps(folder, NOW, 120)
            self.assertEqual(report["file"], latest.name)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["age_seconds"], 10)
            self.assertFalse(report["stale"])
            later, = latest_sweeps(folder, NOW + timedelta(minutes=3), 120)
            self.assertTrue(later["stale"])

    def test_latest_failure_and_incomplete_sweep_are_visible(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            capture(folder, NOW - timedelta(seconds=20))
            capture(folder, NOW - timedelta(seconds=10), failed=True)
            failed, = latest_sweeps(folder, NOW, 120)
            self.assertEqual(failed["status"], "failed")
            capture(folder, NOW, incomplete=True)
            incomplete, = latest_sweeps(folder, NOW, 120)
            self.assertEqual(incomplete["status"], "incomplete")
