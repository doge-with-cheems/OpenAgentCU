import json
import tempfile
import unittest
from pathlib import Path

from oacu.models import Element
from oacu.store import Store, age_seconds
from oacu.tokens import build_snapshot


def make_snapshot(window: str = "记事本", names: tuple[str, ...] = ("确定", "取消")) -> object:
    elements = [
        Element(name=name, control_type="Button", rect=(i * 100, 10, 80, 30),
                window=window, automation_id=f"btn{i}", order=i + 1)
        for i, name in enumerate(names)
    ]
    return build_snapshot(elements, (1920, 1080), {"kept": len(elements)})


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_save_and_read_back(self) -> None:
        snapshot = make_snapshot()
        snapshot_id = self.store.save_snapshot(snapshot)
        tokens = self.store.get_tokens(snapshot_id)
        self.assertEqual([t.name for t in tokens], ["确定", "取消"])
        self.assertEqual(tokens[0].rect, (0, 10, 80, 30))
        self.assertEqual(tokens[1].relations["id"], "btn1")

    def test_latest_by_window(self) -> None:
        self.store.save_snapshot(make_snapshot("记事本"))
        calc = make_snapshot("计算器", ("七", "八"))
        calc_id = self.store.save_snapshot(calc)
        self.assertEqual(self.store.latest_snapshot().id, calc_id)
        self.assertEqual(self.store.latest_snapshot("记事本").token_count, 2)
        self.assertEqual(self.store.latest_snapshot("不存在"), None)

    def test_empty_store(self) -> None:
        self.assertIsNone(self.store.latest_snapshot())

    def test_resolve(self) -> None:
        snapshot_id = self.store.save_snapshot(make_snapshot())
        token = self.store.resolve(snapshot_id, "t0002")
        self.assertIsNotNone(token)
        self.assertEqual(token.name, "取消")
        self.assertIsNone(self.store.resolve(snapshot_id, "t9999"))

    def test_prune_per_window(self) -> None:
        for _ in range(5):
            self.store.save_snapshot(make_snapshot("A"), keep=3)
        for _ in range(2):
            self.store.save_snapshot(make_snapshot("B"), keep=3)
        self.store.prune(keep=3)
        self.assertEqual(self.store.latest_snapshot("A").token_count, 2)
        self.assertEqual(self.store.latest_snapshot("B").token_count, 2)
        self.assertEqual(len(self.store._conn.execute("SELECT id FROM snapshots WHERE window LIKE '%A%'").fetchall()), 3)

    def test_duplicate_snapshot_allowed(self) -> None:
        first = self.store.save_snapshot(make_snapshot())
        second = self.store.save_snapshot(make_snapshot())
        self.assertNotEqual(first, second)

    def test_action_lifecycle(self) -> None:
        snapshot_id = self.store.save_snapshot(make_snapshot())
        self.store.record_action("trace-1", "点击确定", snapshot_id)
        record = self.store.get_action("trace-1")
        self.assertEqual(record["status"], "pending")
        self.store.update_action(
            "trace-1", status="ok", plan={"steps": []}, ir={"steps": []}, snapshot_id=snapshot_id
        )
        record = self.store.get_action("trace-1")
        self.assertEqual(record["status"], "ok")
        self.assertEqual(json.loads(record["plan"]), {"steps": []})

    def test_age_seconds(self) -> None:
        from datetime import datetime, timedelta

        past = (datetime.now().astimezone() - timedelta(seconds=10)).isoformat(timespec="seconds")
        self.assertGreaterEqual(age_seconds(past), 9)
        self.assertEqual(age_seconds("not-a-date"), float("inf"))


if __name__ == "__main__":
    unittest.main()
