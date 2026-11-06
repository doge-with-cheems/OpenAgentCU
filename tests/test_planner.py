import unittest

from oacu.errors import NoMatch
from oacu.models import Token
from oacu.planner import make_plan, match_token


def tokens() -> list[Token]:
    return [
        Token("t0001", "无标题 - 记事本", "Window", (100, 100, 800, 600), order=1),
        Token("t0002", "文本编辑器", "Edit", (110, 170, 780, 510), order=2),
        Token("t0003", "计算器", "Window", (1000, 200, 320, 520), order=3),
        Token("t0004", "七", "Button", (1020, 300, 60, 60), order=4),
        Token("t0005", "等于", "Button", (1200, 560, 60, 60), order=5),
    ]


class PlannerTests(unittest.TestCase):
    def test_click_matches_window(self) -> None:
        plan = make_plan("点击记事本", tokens())
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].op, "click")
        self.assertEqual(plan.steps[0].token_id, "t0001")
        self.assertGreaterEqual(plan.steps[0].score, 0.8)

    def test_type_with_target(self) -> None:
        plan = make_plan("在文本编辑器输入你好", tokens())
        step = plan.steps[0]
        self.assertEqual(step.op, "set_value")
        self.assertEqual(step.token_id, "t0002")
        self.assertEqual(step.value, "你好")

    def test_type_without_target_uses_single_edit(self) -> None:
        plan = make_plan("输入你好", tokens())
        self.assertEqual(plan.steps[0].token_id, "t0002")
        self.assertEqual(plan.steps[0].value, "你好")

    def test_type_value_before_target(self) -> None:
        plan = make_plan("输入“你好”到文本编辑器", tokens())
        self.assertEqual(plan.steps[0].value, "你好")
        self.assertEqual(plan.steps[0].token_id, "t0002")

    def test_double_click(self) -> None:
        plan = make_plan("双击计算器", tokens())
        self.assertEqual(plan.steps[0].op, "double_click")
        self.assertEqual(plan.steps[0].token_id, "t0003")

    def test_scroll(self) -> None:
        plan = make_plan("在计算器向下滚动3次", tokens())
        step = plan.steps[0]
        self.assertEqual(step.op, "scroll")
        self.assertEqual(step.direction, "down")
        self.assertEqual(step.times, 3)

    def test_key(self) -> None:
        plan = make_plan("按键回车", tokens())
        self.assertEqual(plan.steps[0].op, "key")
        self.assertEqual(plan.steps[0].keys, "{ENTER}")

    def test_key_combo(self) -> None:
        plan = make_plan("按下CTRL+S", tokens())
        self.assertEqual(plan.steps[0].keys, "ctrl+s")

    def test_multi_clause(self) -> None:
        plan = make_plan("点击七然后点击等于", tokens())
        self.assertEqual([s.token_id for s in plan.steps], ["t0004", "t0005"])

    def test_missing_target_raises_with_candidates(self) -> None:
        with self.assertRaises(NoMatch) as ctx:
            make_plan("点击保存", tokens())
        self.assertIn("候选", ctx.exception.detail or "")

    def test_unknown_verb_raises(self) -> None:
        with self.assertRaises(NoMatch):
            make_plan("把窗口移到右边", tokens())

    def test_exact_beats_contains(self) -> None:
        extra = tokens() + [Token("t0006", "七", "Text", (10, 10, 10, 10), order=0)]
        token, score, _ = match_token("七", extra)
        self.assertEqual(token.id, "t0006")
        self.assertEqual(score, 1.0)

    def test_plan_to_dict(self) -> None:
        plan = make_plan("点击七然后输入你好到文本编辑器", tokens())
        data = plan.to_dict()
        self.assertEqual(data["instruction"], "点击七然后输入你好到文本编辑器")
        self.assertEqual(len(data["steps"]), 2)
        self.assertEqual(data["steps"][1]["value"], "你好")

    # ---------------------------------------------------------- bugfix coverage
    def test_open_chrome_launches_app(self) -> None:
        plan = make_plan("打开 Google Chrome 浏览器", tokens())
        ops = [s.op for s in plan.steps]
        self.assertEqual(ops[0], "launch")
        self.assertEqual(plan.steps[0].value, "Google Chrome")
        self.assertIn("wait", ops)

    def test_start_chrome_launches_app(self) -> None:
        plan = make_plan("启动 Chrome", tokens())
        self.assertEqual(plan.steps[0].op, "launch")
        self.assertEqual(plan.steps[0].value, "Chrome")

    def test_open_youtube_is_url(self) -> None:
        plan = make_plan("打开 youtube", tokens())
        self.assertEqual(plan.steps[0].op, "open_url")
        self.assertEqual(plan.steps[0].value, "https://www.youtube.com")

    def test_search_opens_google(self) -> None:
        plan = make_plan("搜索 爱泼斯坦 资料", tokens())
        self.assertEqual(plan.steps[0].op, "open_url")
        self.assertIn("google.com/search", plan.steps[0].value)
        self.assertIn("%E7%88%B1", plan.steps[0].value)

    def test_youtube_search(self) -> None:
        plan = make_plan("在 youtube 搜索 the other paradise official mv", tokens())
        self.assertEqual(plan.steps[0].op, "open_url")
        self.assertIn("youtube.com/results", plan.steps[0].value)
        self.assertIn("search_query=", plan.steps[0].value)

    def test_open_youtube_and_search(self) -> None:
        plan = make_plan("打开 youtube 搜索 the other paradise", tokens())
        self.assertEqual(plan.steps[0].op, "open_url")
        self.assertIn("youtube.com/results", plan.steps[0].value)
        self.assertNotIn("google.com", plan.steps[0].value)

    def test_open_app_and_search(self) -> None:
        plan = make_plan("打开 chrome 搜索爱泼斯坦的资料", tokens())
        self.assertEqual(plan.steps[0].op, "launch")
        self.assertEqual(plan.steps[0].value, "chrome")
        self.assertEqual(plan.steps[2].op, "open_url")

    def test_input_without_target_types_into_focus(self) -> None:
        desktop = [
            Token("t0001", "开始", "Pane", (0, 1040, 48, 40), order=1),
            Token("t0002", "在此键入进行搜索", "Pane", (48, 1040, 344, 40), order=2),
        ]
        plan = make_plan("输入 chrome", desktop)
        self.assertEqual(plan.steps[0].op, "type")
        self.assertEqual(plan.steps[0].value, "chrome")

    def test_input_into_pane_clicks_then_types(self) -> None:
        desktop = [
            Token("t0001", "开始", "Pane", (0, 1040, 48, 40), order=1),
            Token("t0002", "在此键入进行搜索", "Pane", (48, 1040, 344, 40), order=2),
        ]
        plan = make_plan("输入 chrome 到「在此键入进行搜索」", desktop)
        self.assertEqual([s.op for s in plan.steps], ["click", "wait", "type"])
        self.assertEqual(plan.steps[2].value, "chrome")

    def test_quoted_target_is_stripped(self) -> None:
        plan = make_plan("点击「操作中心」", tokens() + [
            Token("t0006", "操作中心，3 个新通知", "Pane", (1867, 1040, 48, 40), order=6),
        ])
        self.assertEqual(plan.steps[0].op, "click")
        self.assertEqual(plan.steps[0].token_name, "操作中心，3 个新通知")

    def test_quoted_comma_does_not_split(self) -> None:
        plan = make_plan("点击「操作中心，3 个新通知」", tokens() + [
            Token("t0006", "操作中心，3 个新通知", "Pane", (1867, 1040, 48, 40), order=6),
        ])
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].token_name, "操作中心，3 个新通知")

    def test_bare_target_then_input(self) -> None:
        desktop = [
            Token("t0001", "在此键入进行搜索", "Pane", (48, 1040, 344, 40), order=1),
        ]
        plan = make_plan("在此键入进行搜索，输入 chrome", desktop)
        self.assertEqual([s.op for s in plan.steps], ["click", "type"])
        self.assertEqual(plan.steps[1].value, "chrome")

    def test_windows_key(self) -> None:
        plan = make_plan("按下 Windows 徽标键打开开始菜单", tokens())
        self.assertEqual(plan.steps[0].op, "key")
        self.assertEqual(plan.steps[0].keys, "{WIN}")

    def test_win_key(self) -> None:
        plan = make_plan("按键 win", tokens())
        self.assertEqual(plan.steps[0].keys, "{WIN}")

    def test_comma_key_list(self) -> None:
        plan = make_plan("按键 c,h,r,o,m,e", tokens())
        self.assertEqual(plan.steps[0].keys, "chrome")

    def test_key_with_description(self) -> None:
        plan = make_plan("按 Ctrl+L 聚焦地址栏", tokens())
        self.assertEqual(plan.steps[0].op, "key")
        self.assertEqual(plan.steps[0].keys, "ctrl+l")

    def test_wait(self) -> None:
        plan = make_plan("等待 2 秒", tokens())
        self.assertEqual(plan.steps[0].op, "wait")
        self.assertEqual(plan.steps[0].ms, 2000)


if __name__ == "__main__":
    unittest.main()
