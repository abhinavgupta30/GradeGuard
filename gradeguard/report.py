"""Report formatting and export routines for GradeGuard.

Enforces teacher approval workflows: unapproved reports cannot be exported.
Exports approved reports to clean .txt and .csv formats.
"""
import csv
import io
from pathlib import Path
from typing import Any, Dict, Optional, Union

from gradeguard.feedback import generate_feedback
from gradeguard.models import Assessment, GradeGuardError, Report, validate_student_id
from gradeguard.scoring import weighted_score


def score_report(
    assessment: Assessment, student_id: str, marks: Dict[str, object]
) -> str:
    """Generate draft score report string (prototype compatibility).

    Student ID is validated to ensure only anonymous codes (e.g., S001) are accepted.
    Reports always begin in DRAFT status requiring teacher review.
    """
    valid_id = validate_student_id(student_id)
    pct, detail = weighted_score(assessment, marks)
    feedback_lines = generate_feedback(assessment, marks)

    out = [
        f"Assessment: {assessment.title}",
        f"Student: {valid_id}",
        f"Weighted score: {pct}%",
        "Feedback (DRAFT, teacher must approve):",
    ]
    out += [f"  - {line}" for line in feedback_lines]
    return "\n".join(out)


def create_report(
    assessment: Assessment, student_id: str, marks: Dict[str, object]
) -> Report:
    """Create a structured Report object in DRAFT status."""
    valid_id = validate_student_id(student_id)
    pct, detail = weighted_score(assessment, marks)
    feedback_lines = generate_feedback(assessment, marks)

    criterion_scores = {c.name: marks[c.name] for c in assessment.criteria}

    return Report(
        assessment_title=assessment.title,
        student_id=valid_id,
        weighted_score=pct,
        criterion_scores=criterion_scores,
        criterion_details=detail,
        feedback=feedback_lines,
        is_approved=False,
    )


def _ensure_approved(report_or_dict: Union[Report, Dict[str, Any]]) -> Dict[str, Any]:
    """Verify that a report is approved before permitting export."""
    if isinstance(report_or_dict, Report):
        if not report_or_dict.is_approved:
            raise GradeGuardError(
                f"Cannot export unapproved report for student "
                f"{report_or_dict.student_id!r}. "
                "Teacher approval is strictly required prior to export."
            )
        return {
            "assessment_title": report_or_dict.assessment_title,
            "student_id": report_or_dict.student_id,
            "weighted_score": report_or_dict.weighted_score,
            "marks": report_or_dict.criterion_scores,
            "feedback": report_or_dict.feedback,
            "is_approved": report_or_dict.is_approved,
            "approved_by": report_or_dict.approved_by or "Teacher",
            "approved_at": report_or_dict.approved_at or "",
        }
    elif isinstance(report_or_dict, dict):
        if not report_or_dict.get("is_approved"):
            stu_id = report_or_dict.get("student_id", "unknown")
            raise GradeGuardError(
                f"Cannot export unapproved report for student {stu_id!r}. "
                "Teacher approval is strictly required prior to export."
            )
        return report_or_dict
    else:
        raise GradeGuardError(
            f"Unsupported report type: {type(report_or_dict).__name__}"
        )


def export_report_txt(
    report_data: Union[Report, Dict[str, Any]],
    assessment: Optional[Assessment] = None,
    filepath: Optional[Union[str, Path]] = None,
) -> str:
    """Export an approved report to formatted text.

    Raises:
        GradeGuardError: If the report has not been approved.
    """
    data = _ensure_approved(report_data)

    lines = [
        "=" * 72,
        "GRADEGUARD ASSESSMENT REPORT (APPROVED)",
        "=" * 72,
        f"Assessment:     {data['assessment_title']}",
        f"Student Code:   {data['student_id']}",
        f"Weighted Score: {data['weighted_score']}%",
        f"Status:         APPROVED by {data.get('approved_by', 'Teacher')}",
    ]
    if data.get("approved_at"):
        lines.append(f"Approved At:    {data['approved_at']}")
    lines.append("-" * 72)
    lines.append("CRITERION BREAKDOWN & FEEDBACK:")

    feedback_list = data.get("feedback", [])
    for item in feedback_list:
        lines.append(f"  - {item}")
    lines.append("=" * 72)

    content = "\n".join(lines) + "\n"
    if filepath:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return content


def export_report_csv(
    report_data: Union[Report, Dict[str, Any]],
    assessment: Optional[Assessment] = None,
    filepath: Optional[Union[str, Path]] = None,
) -> str:
    """Export an approved report to CSV format.

    Raises:
        GradeGuardError: If the report has not been approved.
    """
    data = _ensure_approved(report_data)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "student_id",
        "assessment_title",
        "weighted_score",
        "status",
        "approved_by",
        "approved_at",
        "criterion",
        "mark",
        "max_marks",
        "weight",
        "feedback",
    ])

    crit_map = {}
    if assessment:
        crit_map = {c.name: c for c in assessment.criteria}

    marks = data.get("marks", {})
    feedback_list = data.get("feedback", [])
    # Parse feedback items like "Criterion: feedback text"
    feedback_dict = {}
    for fb in feedback_list:
        if ": " in fb:
            c_name, fb_text = fb.split(": ", 1)
            feedback_dict[c_name.strip()] = fb_text.strip()
        else:
            feedback_dict[fb] = fb

    all_criteria = list(marks.keys()) if marks else list(feedback_dict.keys())
    for c_name in all_criteria:
        c_obj = crit_map.get(c_name)
        mark_val = str(marks.get(c_name, ""))
        max_marks_val = str(c_obj.max_marks) if c_obj else ""
        weight_val = str(c_obj.weight) if c_obj else ""
        fb_text = feedback_dict.get(c_name, "")

        writer.writerow([
            data["student_id"],
            data["assessment_title"],
            str(data["weighted_score"]),
            "APPROVED",
            data.get("approved_by", "Teacher"),
            data.get("approved_at", ""),
            c_name,
            mark_val,
            max_marks_val,
            weight_val,
            fb_text,
        ])

    csv_content = output.getvalue()
    if filepath:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(csv_content)

    return csv_content
