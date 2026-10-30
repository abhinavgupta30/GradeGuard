"""GradeGuard: Privacy-safe assessment rubric grading, scoring, feedback, and storage.

Standard library only for core functionality.
All calculations use exact Decimal arithmetic with single-step half-up rounding.
Never stores student names or student work.
"""
from gradeguard.feedback import (
    band,
    check_bias,
    feedback_for,
    generate_feedback,
)
from gradeguard.models import (
    Assessment,
    Criterion,
    GradeGuardError,
    Report,
    RubricLevel,
    TWO_PLACES,
    _dec,
    default_rubric_levels,
    validate_student_id,
)
from gradeguard.report import (
    create_report,
    export_report_csv,
    export_report_txt,
    score_report,
)
from gradeguard.scoring import weighted_score
from gradeguard.storage import Storage

__version__ = "1.0.0"

__all__ = [
    "Assessment",
    "Criterion",
    "GradeGuardError",
    "Report",
    "RubricLevel",
    "Storage",
    "TWO_PLACES",
    "_dec",
    "band",
    "check_bias",
    "create_report",
    "default_rubric_levels",
    "export_report_csv",
    "export_report_txt",
    "feedback_for",
    "generate_feedback",
    "score_report",
    "validate_student_id",
    "weighted_score",
]
