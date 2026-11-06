"""Money is one integer in bronze; 1 gold = 100 silver = 10000 bronze."""
import unittest

from game.content import money


class MoneyTest(unittest.TestCase):
    def test_split(self):
        self.assertEqual(money.split(193865), (19, 38, 65))
        self.assertEqual(money.split(10000), (1, 0, 0))
        self.assertEqual(money.split(99), (0, 0, 99))
        self.assertEqual(money.split(-5), (0, 0, 0))

    def test_leading_zero_coins_are_hidden(self):
        self.assertEqual(money.parts(4507), [(45, "silver"), (7, "bronze")])
        self.assertEqual(money.parts(0), [(0, "bronze")])
        self.assertEqual(money.parts(10000), [(1, "gold"), (0, "silver"), (0, "bronze")])

    def test_formats(self):
        self.assertEqual(money.format_short(193865), "19g 38s 65b")
        self.assertEqual(money.format_long(50), "50 bronze")
        self.assertEqual(money.format_long(10250), "1 gold 2 silver 50 bronze")


if __name__ == "__main__":
    unittest.main()
