"""Unit tests for models: RubricLevel, Criterion, and Assessment."""
from decimal import Decimal
import pytest

from gradeguard.models import (
    Assessment,
    Criterion,
    GradeGuardError,
    Report,
    RubricLevel,
    _dec,
    validate_student_id,
)


def test_dec_valid_and_invalid():
    assert _dec("12.34", "test") == Decimal("12.34")
    assert _dec(42, "test") == Decimal("42")
    with pytest.raises(GradeGuardError, match="must be a number"):
        _dec("not-a-number", "test")
    with pytest.raises(GradeGuardError, match="must be a finite number"):
        _dec(float("inf"), "test")


def test_validate_student_id_valid_codes():
    assert validate_student_id("S001") == "S001"
    assert validate_student_id("  ANON-42  ") == "ANON-42"
    assert validate_student_id("STU_99") == "STU_99"


def test_validate_student_id_rejects_personal_names_and_work():
    # Names with spaces or commas
    with pytest.raises(GradeGuardError, match="appears to be a real name"):
        validate_student_id("John Smith")
    with pytest.raises(GradeGuardError, match="appears to be a real name"):
        validate_student_id("Smith, Jane")
    # Empty
    with pytest.raises(GradeGuardError, match="cannot be empty"):
        validate_student_id("")
    # Student work / long text
    long_text = "This is an essay written by the student about Shakespeare."
    with pytest.raises(GradeGuardError, match="exceeds 30 characters"):
        validate_student_id(long_text)
    # Invalid characters
    with pytest.raises(GradeGuardError, match="must be an alphanumeric code"):
        validate_student_id("S001@#$")


def test_rubric_level_validation():
    lvl = RubricLevel("Excellent", "8.0", "10.0", "High quality work.")
    assert lvl.name == "Excellent"
    assert lvl.min_mark == Decimal("8.0")
    assert lvl.max_mark == Decimal("10.0")
    assert lvl.matches(Decimal("9.0")) is True
    assert lvl.matches(Decimal("7.9")) is False

    with pytest.raises(GradeGuardError, match="name cannot be empty"):
        RubricLevel("", "1", "2", "desc")
    with pytest.raises(GradeGuardError, match="cannot be negative"):
        RubricLevel("Bad", "-1", "5", "desc")
    with pytest.raises(GradeGuardError, match="cannot exceed max_mark"):
        RubricLevel("Bad", "8", "5", "desc")
    with pytest.raises(GradeGuardError, match="Descriptor.*cannot be empty"):
        RubricLevel("Bad", "1", "5", "   ")


def test_criterion_with_custom_rubric_levels():
    levels = [
        RubricLevel(
            "Poor", Decimal("0"), Decimal("3.9"), "Incomplete attempt."
        ),
        RubricLevel(
            "Basic", Decimal("4.0"), Decimal("6.9"), "Basic understanding."
        ),
        RubricLevel(
            "Good", Decimal("7.0"), Decimal("10.0"), "Thorough and accurate."
        ),
    ]
    crit = Criterion("Analysis", Decimal("50"), Decimal("10"), tuple(levels))
    assert crit.get_level(Decimal("2.5")).name == "Poor"
    assert crit.get_level(Decimal("5.0")).name == "Basic"
    assert crit.get_level(Decimal("8.5")).name == "Good"


def test_assessment_add_criterion_custom_levels_and_validation():
    a = Assessment("History Exam")
    custom_levels = [
        {
            "name": "Low",
            "min_mark": 0,
            "max_mark": 5,
            "descriptor": "Low performance.",
        },
        {
            "name": "High",
            "min_mark": 5.1,
            "max_mark": 10,
            "descriptor": "High performance.",
        },
    ]
    a.add_criterion("Essay", 100, 10, levels=custom_levels)
    a.validate()
    assert len(a.criteria) == 1
    assert len(a.criteria[0].levels) == 2

    # Level exceeding max marks
    bad_levels = [
        {
            "name": "TooHigh",
            "min_mark": 0,
            "max_mark": 15,
            "descriptor": "Invalid range.",
        },
    ]
    a2 = Assessment("T")
    with pytest.raises(GradeGuardError, match="exceeds criterion max_marks"):
        a2.add_criterion("C", 100, 10, levels=bad_levels)


def test_assessment_validation_title_and_weights():
    with pytest.raises(GradeGuardError, match="title cannot be empty"):
        Assessment("").validate()
    with pytest.raises(GradeGuardError, match="has no criteria"):
        Assessment("T").validate()


def test_report_approval_workflow():
    r = Report(
        assessment_title="Essay",
        student_id="S001",
        weighted_score=Decimal("85.00"),
        criterion_scores={"A": Decimal("8.5")},
        criterion_details={"A": Decimal("0.85")},
        feedback=["A: Strong work."],
        is_approved=False,
    )
    assert r.is_approved is False
    assert r.approved_by is None

    r.approve(teacher="Dr. Taylor")
    assert r.is_approved is True
    assert r.approved_by == "Dr. Taylor"
    assert r.approved_at is not None

    with pytest.raises(GradeGuardError, match="Teacher name/ID.*cannot be empty"):
        r.approve(teacher="   ")
