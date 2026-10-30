import sys, os, unittest
from decimal import Decimal
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gradeguard import *


def make(weights=(40, 35, 25)):
    a = Assessment("T")
    for n, w in zip(["A", "B", "C"], weights):
        a.add_criterion(n, w, 10)
    return a


class Tests(unittest.TestCase):
    def test_ac1_weights_must_total_100(self):
        with self.assertRaises(GradeGuardError):
            weighted_score(make((40, 35, 24.9)), {"A": 5, "B": 5, "C": 5})

    def test_ac1_decimal_weights_total_exactly_100(self):
        a = Assessment("T")
        for n, w in [("A", "33.3"), ("B", "33.3"), ("C", "33.4")]:
            a.add_criterion(n, w)
        a.validate()  # must not raise (float 0.1-style drift would break this)

    def test_ac2_known_score(self):
        pct, _ = weighted_score(make(), {"A": 8, "B": 6.5, "C": 4})
        self.assertEqual(pct, Decimal("64.75"))  # 32 + 22.75 + 10

    def test_ac3_half_up_rounding(self):
        a = Assessment("T")
        a.add_criterion("A", 100, 8)
        pct, _ = weighted_score(a, {"A": 1})   # 12.5 exactly
        self.assertEqual(pct, Decimal("12.50"))
        a2 = Assessment("T"); a2.add_criterion("A", 100, 3)
        pct2, _ = weighted_score(a2, {"A": 1})  # 33.333...
        self.assertEqual(pct2, Decimal("33.33"))
        a3 = Assessment("T"); a3.add_criterion("A", 100, 800)
        pct3, _ = weighted_score(a3, {"A": 1})  # 0.125 -> 0.13 half-up
        self.assertEqual(pct3, Decimal("0.13"))

    def test_ac4_marks_out_of_range(self):
        for bad in (-1, 10.01, "abc", float("nan")):
            with self.assertRaises(GradeGuardError):
                weighted_score(make(), {"A": bad, "B": 5, "C": 5})

    def test_ac4_missing_and_unknown_criteria(self):
        with self.assertRaises(GradeGuardError):
            weighted_score(make(), {"A": 5, "B": 5})
        with self.assertRaises(GradeGuardError):
            weighted_score(make(), {"A": 5, "B": 5, "C": 5, "D": 5})

    def test_edge_zero_and_full_marks(self):
        self.assertEqual(weighted_score(make(), {"A": 0, "B": 0, "C": 0})[0], Decimal("0.00"))
        self.assertEqual(weighted_score(make(), {"A": 10, "B": 10, "C": 10})[0], Decimal("100.00"))

    def test_bad_criteria_input(self):
        a = Assessment("T")
        for args in [("", 10), ("X", 0), ("X", 101), ("X", -5), ("X", "nan")]:
            with self.assertRaises(GradeGuardError):
                a.add_criterion(*args)
        a.add_criterion("X", 50)
        with self.assertRaises(GradeGuardError):
            a.add_criterion("x", 50)  # duplicate, case-insensitive

    def test_ac5_feedback_depends_only_on_marks(self):
        a = make()
        r1 = score_report(a, "S001", {"A": 9, "B": 5, "C": 2})
        r2 = score_report(a, "S002", {"A": 9, "B": 5, "C": 2})
        self.assertEqual(r1.split("\n", 2)[2], r2.split("\n", 2)[2])  # same marks, same text

    def test_ac6_report_is_marked_draft_and_anonymous(self):
        r = score_report(make(), "S001", {"A": 9, "B": 5, "C": 2})
        self.assertIn("DRAFT", r)
        self.assertIn("S001", r)

if __name__ == "__main__":
    unittest.main(verbosity=2)
