import re
import unittest

from oacu.models import Element
from oacu.tokens import build_snapshot, build_tokens, clean_name, render_text

LINE_RE = re.compile(r"^\{(\[[^\]]*\])(\[[^\]]*\])(\[[^\]]*\])(\[[^\]]*\])\}$")


def el(name: str, ctype: str = "Button", rect: tuple[int, int, int, int] = (10, 20, 30, 40),
       window: str = "W", parent_name: str = "", aid: str = "", order: int = 0) -> Element:
    return Element(name=name, control_type=ctype, rect=rect, window=window,
                   parent_name=parent_name, automation_id=aid, order=order)


class TokenTests(unittest.TestCase):
    def test_format_has_four_brackets(self) -> None:
        tokens = build_tokens([el("确定", "Button", (1, 2, 3, 4), "W", "对话框", "okButton", 1)])
        line = render_text(tokens)
        match = LINE_RE.match(line)
        self.assertIsNotNone(match, line)
        self.assertIn("[确定]", line)
        self.assertIn("[Button]", line)
        self.assertIn("[1,2,3,4]", line)
        self.assertIn("parent=对话框", line)
        self.assertIn("window=W", line)
        self.assertIn("id=okButton", line)
        self.assertIn("order=1", line)

    def test_deterministic(self) -> None:
        elements = [el("A", order=1), el("B", ctype="Edit", rect=(0, 50, 10, 10), order=2)]
        first = build_snapshot(elements, (1920, 1080))
        second = build_snapshot(elements, (1920, 1080))
        self.assertEqual(first.text, second.text)
        self.assertEqual(first.snapshot_key, second.snapshot_key)

    def test_line_count_matches_tokens(self) -> None:
        elements = [el(f"b{i}", rect=(i * 10, i * 10, 5, 5), order=i + 1) for i in range(5)]
        snapshot = build_snapshot(elements)
        self.assertEqual(len(snapshot.text.splitlines()), len(snapshot.tokens))
        self.assertEqual(len(snapshot.tokens), 5)

    def test_name_sanitized_and_truncated(self) -> None:
        raw = "a[b]\n" + "x" * 100
        name = clean_name(raw, "Text")
        self.assertNotIn("[", name)
        self.assertNotIn("]", name)
        self.assertNotIn("\n", name)
        self.assertLessEqual(len(name), 40)

    def test_empty_name_falls_back_to_type(self) -> None:
        token = build_tokens([el("", "Pane")])[0]
        self.assertEqual(token.name, "Pane")

    def test_rect_and_relations_roundtrip(self) -> None:
        token = build_tokens([el("X", "Edit", (11, 22, 33, 44), "记事本", "父", "15", 3)])[0]
        self.assertEqual(token.rect, (11, 22, 33, 44))
        self.assertEqual(token.relations["order"], "3")
        self.assertEqual(token.relations["window"], "记事本")

    def test_snapshot_lists_windows_once(self) -> None:
        elements = [el("a", window="A"), el("b", window="B"), el("c", window="A")]
        snapshot = build_snapshot(elements)
        self.assertEqual(snapshot.window, ["A", "B"])


if __name__ == "__main__":
    unittest.main()
