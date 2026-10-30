"""Rubric-based feedback generation and bias guard verification."""
from decimal import Decimal
import re
from typing import Dict, List

from gradeguard.models import Assessment, GradeGuardError

# Prohibited terms that indicate bias, personal remarks, or gendered references
GENDERED_WORDS = {
    "he", "she", "him", "her", "his", "hers", "himself", "herself",
    "boy", "girl", "man", "woman", "mr", "mrs", "ms", "miss",
    "sir", "madam", "male", "female", "son", "daughter",
}

PERSONAL_REMARKS = {
    "lazy", "stupid", "dumb", "genius", "clever", "smart",
    "attitude", "behavior", "behaviour", "personality", "appearance",
    "naughty", "polite", "disrespectful", "pleasant", "unpleasant",
}

COMMON_NAMES = {
    "alice", "bob", "charlie", "david", "emma", "john", "jane",
    "mary", "michael", "sarah", "tom",
}

ALL_PROHIBITED_TERMS = GENDERED_WORDS | PERSONAL_REMARKS | COMMON_NAMES
PROHIBITED_REGEX = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(ALL_PROHIBITED_TERMS)) + r")\b",
    re.IGNORECASE,
)


def check_bias(text: str) -> None:
    """Inspect text and raise GradeGuardError if personal or biased words appear.

    Ensures feedback is strictly objective and tied to rubric criteria rather than
    student identity or character traits.
    """
    match = PROHIBITED_REGEX.search(text)
    if match:
        word = match.group(0)
        raise GradeGuardError(
            f"Bias guard violation: feedback contains prohibited term {word!r}"
        )


def validate_feedback_list(feedback_lines: List[str]) -> List[str]:
    """Validate each line in a list of feedback strings against the bias guard."""
    for line in feedback_lines:
        check_bias(line)
    return feedback_lines


def band(ratio: Decimal) -> str:
    """Classify a criterion ratio into a performance band (prototype compatibility)."""
    if ratio >= Decimal("0.8"):
        return "strong"
    if ratio >= Decimal("0.5"):
        return "developing"
    return "needs work"


def feedback_for(detail: Dict[str, Decimal]) -> List[str]:
    """Generate default feedback strings from per-criterion ratios."""
    lines = []
    for name, ratio in detail.items():
        b = band(ratio)
        if b == "strong":
            lines.append(f"{name}: strong work, keep it up.")
        elif b == "developing":
            lines.append(
                f"{name}: developing, review the rubric descriptor for this criterion."
            )
        else:
            lines.append(f"{name}: needs work, please see your teacher for support.")
    return validate_feedback_list(lines)


def generate_feedback(
    assessment: Assessment, marks: Dict[str, object]
) -> List[str]:
    """Generate deterministic, rubric-based feedback for an assessment and marks.

    Two students with identical marks will always receive identical feedback.
    All generated lines are verified by the bias guard.
    """
    lines = []
    for c in assessment.criteria:
        mark = marks[c.name]
        level = c.get_level(mark)
        line = f"{c.name}: {level.descriptor}"
        check_bias(line)
        lines.append(line)
    return lines
