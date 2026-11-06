import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from oacu.context import get_context
from oacu.errors import NoSnapshot
from oacu.models import Element
from oacu.store import Store
from oacu.tokens import build_snapshot


def snapshot(window: str = "记事本", created_at: str | None = None):
    elements = [
        Element(name="确定", control_type="Button", rect=(10, 10, 80, 30), window=window, order=1),
        Element(name="取消", control_type="Button", rect=(110, 10, 80, 30), window=window, order=2),
    ]
    snap = build_snapshot(elements, (1920, 1080), {"kept": 2})
    if created_at:
        snap.created_at = created_at
    return snap


class ContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "ctx.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_no_snapshot_without_refresh(self) -> None:
        with self.assertRaises(NoSnapshot):
            get_context(self.store, refresh=None)

    def test_refresh_when_empty(self) -> None:
        calls = {"n": 0}

        def refresh():
            calls["n"] += 1
            return snapshot()

        ctx = get_context(self.store, refresh=refresh)
        self.assertTrue(ctx.refreshed)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(len(ctx.tokens), 2)
        self.assertIsNotNone(self.store.latest_snapshot())

    def test_fresh_snapshot_does_not_refresh(self) -> None:
        self.store.save_snapshot(snapshot())

        def refresh():
            raise AssertionError("collector must not be called for a fresh snapshot")

        ctx = get_context(self.store, refresh=refresh, max_age_s=30)
        self.assertFalse(ctx.refreshed)
        self.assertEqual(len(ctx.tokens), 2)

    def test_stale_snapshot_refreshes(self) -> None:
        old = (datetime.now().astimezone() - timedelta(seconds=120)).isoformat(timespec="seconds")
        self.store.save_snapshot(snapshot("A", old))
        calls = {"n": 0}

        def refresh():
            calls["n"] += 1
            return snapshot("B")

        ctx = get_context(self.store, refresh=refresh, max_age_s=30)
        self.assertTrue(ctx.refreshed)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(ctx.tokens[0].relations["window"], "B")

    def test_window_filter_triggers_refresh(self) -> None:
        self.store.save_snapshot(snapshot("记事本"))

        def refresh():
            return snapshot("计算器")

        ctx = get_context(self.store, window="计算器", refresh=refresh)
        self.assertTrue(ctx.refreshed)
        self.assertEqual(ctx.snapshot_id, self.store.latest_snapshot().id)


if __name__ == "__main__":
    unittest.main()
