"""Domain models and core data structures for GradeGuard.

Fictional data only. Uses Decimal so all weights, marks, and rounding are exact.
Enforces privacy: only anonymous student codes (e.g., S001) are permitted.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import List, Optional, Tuple

TWO_PLACES = Decimal("0.01")
ANONYMOUS_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,30}$")


class GradeGuardError(ValueError):
    """Raised for any invalid input (bad weight, bad mark, privacy violation)."""


def _dec(value, name: str) -> Decimal:
    """Safely convert value to a finite Decimal, raising GradeGuardError."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise GradeGuardError(f"{name} must be a number, got {value!r}")
    if not d.is_finite():
        raise GradeGuardError(f"{name} must be a finite number")
    return d


def validate_student_id(student_id: str) -> str:
    """Validate that student_id is a short anonymous code (e.g., S001).

    Rejects personal names, whitespace, and student work text to preserve privacy.
    """
    if not isinstance(student_id, str):
        raise GradeGuardError(
            f"Student ID must be a string, got {type(student_id).__name__}"
        )
    code = student_id.strip()
    if not code:
        raise GradeGuardError("Student ID cannot be empty")
    if len(code) > 30:
        raise GradeGuardError(
            "Student ID exceeds 30 characters; student work must never be stored"
        )
    if " " in code or "," in code:
        raise GradeGuardError(
            f"Student ID {student_id!r} appears to be a real name; "
            "only anonymous codes (e.g. S001) are permitted"
        )
    if not ANONYMOUS_ID_PATTERN.match(code):
        raise GradeGuardError(
            f"Invalid student ID {student_id!r}; must be an alphanumeric code like S001"
        )
    return code


@dataclass(frozen=True)
class RubricLevel:
    """Descriptor for a performance level within a criterion mark range."""
    name: str
    min_mark: Decimal
    max_mark: Decimal
    descriptor: str

    def __post_init__(self):
        name_clean = (self.name or "").strip()
        if not name_clean:
            raise GradeGuardError("Rubric level name cannot be empty")
        object.__setattr__(self, "name", name_clean)

        min_d = _dec(self.min_mark, f"min_mark for level {self.name}")
        max_d = _dec(self.max_mark, f"max_mark for level {self.name}")
        if min_d < 0:
            raise GradeGuardError(f"min_mark for {self.name} cannot be negative")
        if min_d > max_d:
            raise GradeGuardError(
                f"min_mark ({min_d}) cannot exceed max_mark ({max_d}) "
                f"for level {self.name}"
            )
        object.__setattr__(self, "min_mark", min_d)
        object.__setattr__(self, "max_mark", max_d)

        desc_clean = (self.descriptor or "").strip()
        if not desc_clean:
            raise GradeGuardError(f"Descriptor for level {self.name} cannot be empty")
        object.__setattr__(self, "descriptor", desc_clean)

    def matches(self, mark: Decimal) -> bool:
        """Return True if mark falls into [min_mark, max_mark]."""
        return self.min_mark <= mark <= self.max_mark


def default_rubric_levels(max_marks: Decimal) -> Tuple[RubricLevel, ...]:
    """Default rubric levels matching the original prototype bands."""
    m = _dec(max_marks, "max_marks")
    return (
        RubricLevel(
            name="Strong",
            min_mark=(m * Decimal("0.8")).quantize(TWO_PLACES),
            max_mark=m,
            descriptor="strong work, keep it up.",
        ),
        RubricLevel(
            name="Developing",
            min_mark=(m * Decimal("0.5")).quantize(TWO_PLACES),
            max_mark=(m * Decimal("0.8")).quantize(TWO_PLACES),
            descriptor="developing, review the rubric descriptor for this criterion.",
        ),
        RubricLevel(
            name="Needs Work",
            min_mark=Decimal("0.00"),
            max_mark=(m * Decimal("0.5")).quantize(TWO_PLACES),
            descriptor="needs work, please see your teacher for support.",
        ),
    )


@dataclass(frozen=True)
class Criterion:
    """An individual assessment criterion with weight, max marks, and rubric levels."""
    name: str
    weight: Decimal      # percent, 0 < weight <= 100
    max_marks: Decimal   # marks available for this criterion
    levels: Tuple[RubricLevel, ...] = field(default_factory=tuple)

    def get_level(self, mark: Decimal) -> RubricLevel:
        """Find the rubric level matching the awarded mark."""
        m = _dec(mark, f"mark for {self.name}")
        # Search descending by min_mark to choose the higher level on boundary
        sorted_levels = sorted(
            self.levels,
            key=lambda lvl: (lvl.min_mark, lvl.max_mark),
            reverse=True,
        )
        for lvl in sorted_levels:
            if lvl.matches(m):
                return lvl
        # Fallback if no explicit level matched (e.g. edge rounding)
        if sorted_levels:
            return sorted_levels[-1]
        raise GradeGuardError(f"No rubric level configured for criterion {self.name}")


@dataclass
class Assessment:
    """A collection of criteria whose weights total exactly 100."""
    title: str
    criteria: List[Criterion] = field(default_factory=list)

    def add_criterion(self, name: str, weight, max_marks=10, levels=None):
        """Add a criterion with percentage weight, max marks, and rubric levels."""
        name = (name or "").strip()
        if not name:
            raise GradeGuardError("criterion name cannot be empty")
        if any(c.name.lower() == name.lower() for c in self.criteria):
            raise GradeGuardError(f"duplicate criterion: {name}")

        w = _dec(weight, "weight")
        m = _dec(max_marks, "max_marks")

        if not (Decimal(0) < w <= Decimal(100)):
            raise GradeGuardError("weight must be above 0 and at most 100")
        if m <= 0:
            raise GradeGuardError("max_marks must be positive")

        if levels is None:
            parsed_levels = default_rubric_levels(m)
        else:
            lvl_list = []
            for item in levels:
                if isinstance(item, RubricLevel):
                    lvl = item
                elif isinstance(item, dict):
                    lvl = RubricLevel(
                        name=item["name"],
                        min_mark=item["min_mark"],
                        max_mark=item["max_mark"],
                        descriptor=item["descriptor"],
                    )
                else:
                    raise GradeGuardError(f"Invalid rubric level format: {item!r}")
                if lvl.max_mark > m:
                    raise GradeGuardError(
                        f"Level {lvl.name} max_mark ({lvl.max_mark}) "
                        f"exceeds criterion max_marks ({m})"
                    )
                lvl_list.append(lvl)
            if not lvl_list:
                raise GradeGuardError("levels cannot be empty when explicitly provided")
            parsed_levels = tuple(lvl_list)

        self.criteria.append(Criterion(name, w, m, parsed_levels))

    def validate(self):
        """Weights must total exactly 100 before any grading is allowed."""
        title_clean = (self.title or "").strip()
        if not title_clean:
            raise GradeGuardError("assessment title cannot be empty")
        if not self.criteria:
            raise GradeGuardError("assessment has no criteria")
        total = sum(c.weight for c in self.criteria)
        if total != Decimal(100):
            raise GradeGuardError(f"weights total {total}%, must be exactly 100%")


@dataclass
class Report:
    """A scored assessment report with approval workflow."""
    assessment_title: str
    student_id: str
    weighted_score: Decimal
    criterion_scores: dict
    criterion_details: dict
    feedback: List[str]
    is_approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    def approve(self, teacher: str = "Teacher"):
        """Approve the draft report so it is ready for student release / export."""
        teacher_clean = (teacher or "").strip()
        if not teacher_clean:
            raise GradeGuardError(
                "Teacher name/ID approving the report cannot be empty"
            )
        self.is_approved = True
        self.approved_by = teacher_clean
        self.approved_at = datetime.now(timezone.utc).isoformat()
