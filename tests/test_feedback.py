"""Unit tests for feedback generation, rubric levels, and bias guard."""
from decimal import Decimal
import pytest

from gradeguard.feedback import (
    band,
    check_bias,
    feedback_for,
    generate_feedback,
)
from gradeguard.models import Assessment, GradeGuardError, RubricLevel


def test_band_classification():
    assert band(Decimal("0.85")) == "strong"
    assert band(Decimal("0.80")) == "strong"
    assert band(Decimal("0.79")) == "developing"
    assert band(Decimal("0.50")) == "developing"
    assert band(Decimal("0.49")) == "needs work"
    assert band(Decimal("0.00")) == "needs work"


def test_feedback_for_default_bands():
    detail = {
        "Structure": Decimal("0.9"),
        "Research": Decimal("0.6"),
        "Grammar": Decimal("0.3"),
    }
    lines = feedback_for(detail)
    assert lines[0] == "Structure: strong work, keep it up."
    expected_dev = (
        "Research: developing, review the rubric descriptor for this criterion."
    )
    assert lines[1] == expected_dev
    assert lines[2] == "Grammar: needs work, please see your teacher for support."


def test_generate_feedback_with_custom_rubric_levels():
    a = Assessment("Writing Assessment")
    custom_levels = [
        RubricLevel(
            "Poor", Decimal("0"), Decimal("4.9"),
            "Needs substantive revision of ideas."
        ),
        RubricLevel(
            "Proficient", Decimal("5.0"), Decimal("7.9"),
            "Demonstrates solid core concepts."
        ),
        RubricLevel(
            "Advanced", Decimal("8.0"), Decimal("10.0"),
            "Exhibits exceptional synthesis and depth."
        ),
    ]
    a.add_criterion("Clarity", 100, 10, levels=custom_levels)

    low_fb = generate_feedback(a, {"Clarity": Decimal("3.5")})
    assert low_fb == ["Clarity: Needs substantive revision of ideas."]

    mid_fb = generate_feedback(a, {"Clarity": Decimal("6.0")})
    assert mid_fb == ["Clarity: Demonstrates solid core concepts."]

    high_fb = generate_feedback(a, {"Clarity": Decimal("9.5")})
    assert high_fb == ["Clarity: Exhibits exceptional synthesis and depth."]


def test_bias_guard_rejects_gendered_terms():
    prohibited_samples = [
        "She demonstrated a solid grasp of the subject.",
        "His work meets the benchmark.",
        "The boy was capable in this section.",
        "Feedback for Mr. Smith's class.",
        "He should improve evidence synthesis.",
    ]
    for sample in prohibited_samples:
        with pytest.raises(GradeGuardError, match="Bias guard violation"):
            check_bias(sample)


def test_bias_guard_rejects_personal_remarks():
    personal_samples = [
        "The student is very smart and talented.",
        "Appears lazy and careless in calculations.",
        "Needs to improve classroom attitude and behavior.",
        "A clever student who grasps topics quickly.",
    ]
    for sample in personal_samples:
        with pytest.raises(GradeGuardError, match="Bias guard violation"):
            check_bias(sample)


def test_bias_guard_rejects_common_names():
    name_samples = [
        "Alice presented great analysis.",
        "Good effort from John today.",
    ]
    for sample in name_samples:
        with pytest.raises(GradeGuardError, match="Bias guard violation"):
            check_bias(sample)


def test_bias_guard_allows_objective_academic_descriptors():
    clean_samples = [
        "Arguments are supported by peer-reviewed evidence.",
        "Calculations follow established formulas accurately.",
        "The response adheres to formatting guidelines.",
        "Developing, review the rubric descriptor for this criterion.",
        "Strong work, keep it up.",
    ]
    for sample in clean_samples:
        check_bias(sample)  # must not raise


def test_identical_marks_yield_identical_feedback():
    """Proof that feedback generation is strictly deterministic."""
    a = Assessment("Biology Lab")
    a.add_criterion("Hypothesis", 50, 10)
    a.add_criterion("Methodology", 50, 10)

    marks = {"Hypothesis": Decimal("8.0"), "Methodology": Decimal("5.5")}

    fb_student_1 = generate_feedback(a, marks)
    fb_student_2 = generate_feedback(a, marks)

    assert fb_student_1 == fb_student_2
    assert len(fb_student_1) == 2
    assert "Hypothesis: strong work, keep it up." in fb_student_1
    expected_dev = (
        "Methodology: developing, review the rubric descriptor for this criterion."
    )
    assert expected_dev in fb_student_1
