"""New inert controls for the exact expression in the adjacent patch.

No operational module, request, grant, file or native API is imported.
"""
import unittest


def corrected_predicate(admission):
    # Exact accepted expression; this wrapper is a new public test scaffold.
    return type(admission) is dict and bool(admission)


class BooleanAdmissionControls(unittest.TestCase):
    def test_nonempty_mapping_returns_identity_true(self):
        value = {"example": 1}
        old = type(value) is dict and value
        self.assertIsNot(old, True)
        self.assertIs(corrected_predicate(value), True)

    def test_empty_and_non_mapping_values_refused(self):
        for value in ({}, None, False, True, 1, 1.0, [], [1], "mapping"):
            with self.subTest(type=type(value).__name__):
                self.assertIs(corrected_predicate(value), False)

    def test_mapping_subclass_is_not_exact_mapping(self):
        class Derived(dict):
            pass
        self.assertIs(corrected_predicate(Derived(example=1)), False)


if __name__ == "__main__":
    unittest.main()
