"""Scoring calculations using Decimal arithmetic and single-step half-up rounding."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Tuple

from gradeguard.models import Assessment, GradeGuardError, TWO_PLACES, _dec


def weighted_score(
    assessment: Assessment, marks: Dict[str, object]
) -> Tuple[Decimal, Dict[str, Decimal]]:
    """Calculate weighted percentage and per-criterion ratios.

    Args:
        assessment: Assessment containing criteria whose weights total 100%.
        marks: Mapping of {criterion_name: mark_awarded}.

    Returns:
        (total_percentage, per_criterion_ratios)
        Rounding occurs only once at the end using ROUND_HALF_UP.

    Raises:
        GradeGuardError: On missing, unknown, non-numeric, or out-of-range marks.
    """
    assessment.validate()
    names = {c.name for c in assessment.criteria}
    mark_names = set(marks.keys())

    extra = mark_names - names
    missing = names - mark_names
    if extra:
        raise GradeGuardError(f"unknown criteria: {sorted(extra)}")
    if missing:
        raise GradeGuardError(f"missing marks for: {sorted(missing)}")

    total = Decimal(0)
    detail: Dict[str, Decimal] = {}

    for c in assessment.criteria:
        got = _dec(marks[c.name], f"marks for {c.name}")
        if got < 0 or got > c.max_marks:
            raise GradeGuardError(
                f"marks for {c.name} must be between 0 and {c.max_marks}"
            )

        ratio = got / c.max_marks
        detail[c.name] = ratio
        total += ratio * c.weight

    # Round once, at the very end
    final_percentage = total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return final_percentage, detail
