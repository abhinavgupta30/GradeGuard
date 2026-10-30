"""Unit tests for scoring, exact Decimal arithmetic, and rounding."""
from decimal import Decimal
import pytest

from gradeguard.models import Assessment, GradeGuardError
from gradeguard.scoring import weighted_score


def test_three_way_decimal_split_33_3_33_3_33_4():
    a = Assessment("Tri-Section")
    a.add_criterion("Section A", Decimal("33.3"), 10)
    a.add_criterion("Section B", Decimal("33.3"), 10)
    a.add_criterion("Section C", Decimal("33.4"), 10)
    a.validate()

    # All full marks: should yield exactly 100.00%
    score, _ = weighted_score(
        a, {"Section A": 10, "Section B": 10, "Section C": 10}
    )
    assert score == Decimal("100.00")

    # Half marks across all: should yield 50.00%
    score_half, _ = weighted_score(
        a, {"Section A": 5, "Section B": 5, "Section C": 5}
    )
    assert score_half == Decimal("50.00")


def test_rounding_boundaries_half_up_cases():
    """Verify x.xx5 rounds UP and x.xx499 rounds DOWN under ROUND_HALF_UP."""
    # Case 1: 50.005 -> 50.01
    a = Assessment("R1")
    a.add_criterion("C1", 100, 200)
    pct1, _ = weighted_score(a, {"C1": Decimal("100.01")})
    assert pct1 == Decimal("50.01")

    # Case 2: 50.0049 -> 50.00
    pct2, _ = weighted_score(a, {"C1": Decimal("100.0098")})
    assert pct2 == Decimal("50.00")

    # Case 3: 12.125 -> 12.13
    a2 = Assessment("R2")
    a2.add_criterion("C1", 100, 800)
    pct3, _ = weighted_score(a2, {"C1": 97})
    assert pct3 == Decimal("12.13")

    # Case 4: 99.995 -> 100.00
    a3 = Assessment("R3")
    a3.add_criterion("C1", 100, 1000)
    pct4, _ = weighted_score(a3, {"C1": Decimal("999.95")})
    assert pct4 == Decimal("100.00")


def test_zero_and_full_marks_boundary():
    a = Assessment("Limits")
    a.add_criterion("C1", 60, 20)
    a.add_criterion("C2", 40, 50)

    score_zero, _ = weighted_score(a, {"C1": 0, "C2": 0})
    assert score_zero == Decimal("0.00")

    score_full, _ = weighted_score(a, {"C1": 20, "C2": 50})
    assert score_full == Decimal("100.00")


def test_invalid_mark_ranges_and_types():
    a = Assessment("Validation")
    a.add_criterion("C1", 100, 10)

    # Negative mark
    with pytest.raises(GradeGuardError, match="must be between 0 and 10"):
        weighted_score(a, {"C1": -0.1})

    # Exceeding max marks
    with pytest.raises(GradeGuardError, match="must be between 0 and 10"):
        weighted_score(a, {"C1": 10.01})

    # Non-numeric
    with pytest.raises(GradeGuardError, match="must be a number"):
        weighted_score(a, {"C1": "invalid"})

    # Non-finite
    with pytest.raises(GradeGuardError, match="must be a finite number"):
        weighted_score(a, {"C1": float("nan")})
    with pytest.raises(GradeGuardError, match="must be a finite number"):
        weighted_score(a, {"C1": float("inf")})


def test_missing_and_extra_criteria_errors():
    a = Assessment("CriteriaCheck")
    a.add_criterion("A", 50, 10)
    a.add_criterion("B", 50, 10)

    with pytest.raises(GradeGuardError, match="missing marks for: \\['B'\\]"):
        weighted_score(a, {"A": 5})

    with pytest.raises(GradeGuardError, match="unknown criteria: \\['C'\\]"):
        weighted_score(a, {"A": 5, "B": 5, "C": 5})
