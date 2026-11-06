import json
import unittest
from pathlib import Path

from oacu.models import RawElement
from oacu.uia.normalize import normalize

FIXTURE = Path(__file__).resolve().parents[1] / "tools" / "fixture_desktop.json"


def load_raw() -> list[RawElement]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [RawElement.from_dict(item) for item in data["elements"]]


class NormalizeTests(unittest.TestCase):
    def test_fixture_stats(self) -> None:
        elements, stats = normalize(load_raw())
        self.assertEqual(stats.raw, 9)
        self.assertEqual(stats.kept, 7)
        self.assertEqual(stats.dropped, 2)
        self.assertEqual(stats.reasons.get("zero_area"), 1)
        self.assertEqual(stats.reasons.get("duplicate"), 1)

    def test_zero_area_dropped(self) -> None:
        raw = RawElement(name="hidden", control_type="Pane", rect=(0, 0, 0, 0))
        elements, stats = normalize([raw])
        self.assertEqual(elements, [])
        self.assertEqual(stats.reasons.get("zero_area"), 1)

    def test_empty_leaf_dropped_but_container_kept(self) -> None:
        raws = [
            RawElement(name="", control_type="Pane", rect=(0, 0, 100, 100), parent=-1, depth=0),
            RawElement(name="", control_type="Pane", rect=(10, 10, 20, 20), parent=0, depth=1),
        ]
        elements, stats = normalize(raws)
        self.assertEqual(len(elements), 1)
        self.assertEqual(stats.reasons.get("empty_leaf"), 1)

    def test_window_and_parent_name(self) -> None:
        elements, _ = normalize(load_raw())
        edit = next(e for e in elements if e.control_type == "Edit")
        self.assertEqual(edit.window, "无标题 - 记事本")
        self.assertEqual(edit.parent_name, "无标题 - 记事本")

    def test_window_filter(self) -> None:
        elements, stats = normalize(load_raw(), window="计算器")
        self.assertEqual(len(elements), 3)
        self.assertTrue(all("计算器" in e.window for e in elements))
        self.assertEqual(stats.kept, 3)

    def test_duplicate_keeps_first(self) -> None:
        raws = [
            RawElement(name="A", control_type="Button", rect=(0, 0, 10, 10), parent=-1, depth=0),
            RawElement(name="A", control_type="Button", rect=(0, 0, 10, 10), parent=-1, depth=0),
        ]
        elements, stats = normalize(raws)
        self.assertEqual(len(elements), 1)
        self.assertEqual(stats.reasons.get("duplicate"), 1)

    def test_self_parent_is_root(self) -> None:
        raw = RawElement(name="W", control_type="Window", rect=(0, 0, 10, 10), parent=0, depth=0)
        elements, _ = normalize([raw])
        self.assertEqual(elements[0].window, "W")

    def test_minimized_coordinates_dropped(self) -> None:
        raw = RawElement(name="Spotify", control_type="Pane", rect=(-32000, -32000, 1600, 900),
                         parent=-1, depth=0)
        elements, stats = normalize([raw])
        self.assertEqual(elements, [])
        self.assertEqual(stats.reasons.get("offscreen"), 1)

    def test_offscreen_flag_kept_when_rect_is_visible(self) -> None:
        # Some Chromium panes report IsOffscreen=True while still being useful.
        raw = RawElement(name="Chrome Legacy Window", control_type="Pane", rect=(10, 10, 200, 200),
                         parent=-1, depth=0, offscreen=True)
        elements, _stats = normalize([raw])
        self.assertEqual(len(elements), 1)

    def test_one_pixel_noise_dropped(self) -> None:
        raw = RawElement(name="StatusBar", control_type="StatusBar", rect=(0, 0, 1, 1),
                         parent=-1, depth=0)
        elements, stats = normalize([raw])
        self.assertEqual(elements, [])
        self.assertEqual(stats.reasons.get("zero_area"), 1)

    def test_pipeline_window_filter_after_full_capture(self) -> None:
        from oacu.pipeline import capture_snapshot

        snapshot = capture_snapshot(backend="fake", fixture=str(FIXTURE), window="计算器")
        self.assertEqual(len(snapshot.tokens), 3)
        self.assertTrue(all("计算器" in token.relations["window"] for token in snapshot.tokens))


if __name__ == "__main__":
    unittest.main()
