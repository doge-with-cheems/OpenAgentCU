import unittest

from oacu.models import Element
from oacu.uia.order import order_elements, row_band


def el(name: str, rect: tuple[int, int, int, int], window: str = "W") -> Element:
    return Element(name=name, control_type="Button", rect=rect, window=window)


class OrderTests(unittest.TestCase):
    def test_two_rows_three_columns(self) -> None:
        cells = [
            el("r2c2", (200, 200, 50, 40)),
            el("r1c3", (400, 100, 50, 40)),
            el("r2c1", (100, 200, 50, 40)),
            el("r1c1", (100, 100, 50, 40)),
            el("r2c3", (400, 200, 50, 40)),
            el("r1c2", (200, 100, 50, 40)),
        ]
        ordered = order_elements(cells)
        self.assertEqual([e.name for e in ordered], ["r1c1", "r1c2", "r1c3", "r2c1", "r2c2", "r2c3"])
        self.assertEqual([e.order for e in ordered], [1, 2, 3, 4, 5, 6])

    def test_jitter_keeps_reading_order(self) -> None:
        items = [
            el("a", (100, 109, 40, 20)),
            el("b", (200, 100, 40, 20)),
            el("c", (300, 91, 40, 20)),
        ]
        ordered = order_elements(items)
        self.assertEqual([e.name for e in ordered], ["a", "b", "c"])
        self.assertEqual(row_band(items[1]), row_band(items[0]))

    def test_negative_coordinates(self) -> None:
        items = [
            el("second", (-500, 100, 50, 50)),
            el("first", (-1200, 100, 50, 50)),
        ]
        ordered = order_elements(items)
        self.assertEqual([e.name for e in ordered], ["first", "second"])

    def test_windows_keep_first_appearance(self) -> None:
        items = [
            el("w2a", (100, 100, 10, 10), window="B"),
            el("w1a", (100, 100, 10, 10), window="A"),
            el("w2b", (100, 200, 10, 10), window="B"),
            el("w1b", (100, 200, 10, 10), window="A"),
        ]
        ordered = order_elements(items)
        self.assertEqual([e.name for e in ordered], ["w2a", "w2b", "w1a", "w1b"])

    def test_parent_precedes_children(self) -> None:
        parent = el("窗口", (0, 0, 800, 600))
        child = el("按钮", (100, 100, 50, 30))
        other = el("兄弟", (200, 100, 50, 30))
        child.parent_ref = 0
        other.parent_ref = 0
        ordered = order_elements([parent, child, other])
        self.assertEqual([e.name for e in ordered], ["窗口", "按钮", "兄弟"])

    def test_nested_parent_precedes_grandchild(self) -> None:
        root = el("窗口", (0, 0, 800, 600))
        pane = el("面板", (50, 50, 600, 400))
        deep = el("深层按钮", (100, 100, 50, 30))
        pane.parent_ref = 0
        deep.parent_ref = 1
        ordered = order_elements([root, pane, deep])
        self.assertEqual([e.name for e in ordered], ["窗口", "面板", "深层按钮"])

    def test_order_is_renumbered(self) -> None:
        items = [el("a", (100, 100, 10, 10)), el("b", (100, 300, 10, 10))]
        order_elements(items)
        self.assertEqual([e.order for e in items], [1, 2])


if __name__ == "__main__":
    unittest.main()
