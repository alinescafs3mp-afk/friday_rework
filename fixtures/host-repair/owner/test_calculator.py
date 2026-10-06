import unittest
from calculator import add
class CalculatorTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(7, 5), 12)
        self.assertEqual(add(-2, 3), 1)
        self.assertEqual(add(0, 0), 0)
if __name__ == "__main__": unittest.main()
