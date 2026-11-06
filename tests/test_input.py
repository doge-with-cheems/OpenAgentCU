import unittest

from oacu.input import (
    InputError,
    click,
    drag,
    key_press,
    mouse_position,
    normalize_keys,
    screen_info,
    scroll,
    type_text,
    validate_point,
)


class InputTests(unittest.TestCase):
    def test_screen_info(self) -> None:
        info = screen_info()
        self.assertGreaterEqual(info["width"], 1)
        self.assertGreaterEqual(info["height"], 1)

    def test_mouse_position_is_int_pair(self) -> None:
        x, y = mouse_position()
        self.assertIsInstance(x, int)
        self.assertIsInstance(y, int)

    def test_validate_point_ok(self) -> None:
        info = screen_info()
        self.assertEqual(validate_point(info["x"], info["y"]),
                         (info["x"], info["y"]))

    def test_validate_point_out_of_bounds(self) -> None:
        with self.assertRaises(InputError):
            validate_point(10 ** 7, 10 ** 7)
        with self.assertRaises(InputError):
            validate_point(-10 ** 7, -10 ** 7)

    def test_key_aliases(self) -> None:
        self.assertEqual(normalize_keys("win"), "{WIN}")
        self.assertEqual(normalize_keys("徽标键"), "{WIN}")
        self.assertEqual(normalize_keys("回车"), "{ENTER}")
        self.assertEqual(normalize_keys("c,h,r,o,m,e"), "chrome")
        self.assertEqual(normalize_keys("ctrl+s"), "ctrl+s")

    def test_bad_button_rejected_before_input(self) -> None:
        with self.assertRaises(InputError):
            click(button="sideways")

    def test_scroll_zero_rejected(self) -> None:
        with self.assertRaises(InputError):
            scroll(dy=0, dx=0)

    def test_type_empty_rejected(self) -> None:
        with self.assertRaises(InputError):
            type_text("")

    def test_key_empty_rejected(self) -> None:
        with self.assertRaises(InputError):
            key_press("")

    def test_drag_invalid_point_rejected(self) -> None:
        with self.assertRaises(InputError):
            drag(10 ** 7, 10 ** 7, 0, 0)

    def test_drag_point_mismatch(self) -> None:
        with self.assertRaises(InputError):
            from oacu import input as input_mod

            input_mod.move(999999, 999999)


if __name__ == "__main__":
    unittest.main()
