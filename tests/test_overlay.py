import unittest

from oacu import overlay, virtual


class OverlayTests(unittest.TestCase):
    def test_cursor_is_half_of_201_size(self) -> None:
        self.assertEqual(overlay.SIZE, 36)
        self.assertEqual(overlay.CROSS_HALF, 9)
        self.assertEqual(overlay.CROSS_WIDTH, 2)

    def test_pointer_limit_matches_virtual_module(self) -> None:
        self.assertEqual(overlay.MAX_POINTERS, virtual.MAX_POINTERS)
        self.assertEqual(virtual.MAX_POINTERS, 4)


if __name__ == "__main__":
    unittest.main()
