"""Unit tests for report generation, approval, and text/csv export."""
from decimal import Decimal
import pytest

from gradeguard.models import Assessment, GradeGuardError
from gradeguard.report import (
    create_report,
    export_report_csv,
    export_report_txt,
    score_report,
)


def make_assessment():
    a = Assessment("Literature Essay")
    a.add_criterion("Thesis", 40, 10)
    a.add_criterion("Evidence", 35, 10)
    a.add_criterion("Structure", 25, 10)
    return a


def test_score_report_formatting():
    a = make_assessment()
    marks = {"Thesis": 8, "Evidence": 6.5, "Structure": 4}
    report_text = score_report(a, "S101", marks)

    assert "Assessment: Literature Essay" in report_text
    assert "Student: S101" in report_text
    assert "Weighted score: 64.75%" in report_text
    assert "Feedback (DRAFT, teacher must approve):" in report_text
    assert "Thesis: strong work, keep it up." in report_text


def test_unapproved_report_cannot_be_exported():
    a = make_assessment()
    report = create_report(
        a, "S101", {"Thesis": 8, "Evidence": 6.5, "Structure": 4}
    )
    assert report.is_approved is False

    # Attempting to export unapproved Report object
    with pytest.raises(GradeGuardError, match="Teacher approval is strictly required"):
        export_report_txt(report)

    with pytest.raises(GradeGuardError, match="Teacher approval is strictly required"):
        export_report_csv(report)

    # Attempting to export unapproved dict record
    dict_record = {
        "assessment_title": "Literature Essay",
        "student_id": "S101",
        "weighted_score": Decimal("64.75"),
        "marks": {"Thesis": 8, "Evidence": 6.5, "Structure": 4},
        "feedback": ["Thesis: strong work, keep it up."],
        "is_approved": False,
    }
    with pytest.raises(GradeGuardError, match="Teacher approval is strictly required"):
        export_report_txt(dict_record)
    with pytest.raises(GradeGuardError, match="Teacher approval is strictly required"):
        export_report_csv(dict_record)


def test_approved_report_exports_to_txt_and_csv(tmp_path):
    a = make_assessment()
    report = create_report(
        a, "S101", {"Thesis": 8, "Evidence": 6.5, "Structure": 4}
    )
    report.approve(teacher="Dr. Johnson")

    txt_path = tmp_path / "report_S101.txt"
    txt_out = export_report_txt(report, assessment=a, filepath=txt_path)

    assert "GRADEGUARD ASSESSMENT REPORT (APPROVED)" in txt_out
    assert "Literature Essay" in txt_out
    assert "Student Code:   S101" in txt_out
    assert "Weighted Score: 64.75%" in txt_out
    assert "APPROVED by Dr. Johnson" in txt_out
    assert txt_path.exists()
    assert txt_path.read_text(encoding="utf-8") == txt_out

    csv_path = tmp_path / "report_S101.csv"
    csv_out = export_report_csv(report, assessment=a, filepath=csv_path)

    assert "student_id,assessment_title,weighted_score,status" in csv_out
    assert "S101,Literature Essay,64.75,APPROVED,Dr. Johnson" in csv_out
    assert 'Thesis,8,10,40,"strong work, keep it up."' in csv_out
    assert csv_path.exists()
    assert csv_path.read_text(encoding="utf-8") == csv_out
