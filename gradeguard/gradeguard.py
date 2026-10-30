"""Backwards-compatibility module for the legacy prototype entrypoint.

All functionality is modularised under gradeguard.models, gradeguard.scoring,
gradeguard.feedback, gradeguard.storage, gradeguard.report, and gradeguard.cli.
"""
from gradeguard import *  # noqa: F401, F403

if __name__ == "__main__":
    a = Assessment("Sample Essay 1")
    a.add_criterion("Argument", 40, 10)
    a.add_criterion("Evidence", 35, 10)
    a.add_criterion("Clarity", 25, 10)
    print(score_report(a, "S001", {"Argument": 8, "Evidence": 6.5, "Clarity": 4}))
