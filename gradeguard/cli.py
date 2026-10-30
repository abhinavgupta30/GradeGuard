"""Command line interface for GradeGuard using argparse.

Commands:
    create-assessment   Initialize an assessment title
    add-criterion       Add a weighted criterion with rubric levels
    grade               Grade a student by anonymous ID (stored as DRAFT)
    approve             Approve a draft score report by teacher ID
    export              Export an approved report to .txt or .csv
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Dict, List, Optional

from gradeguard.feedback import generate_feedback
from gradeguard.models import (
    Assessment,
    GradeGuardError,
    RubricLevel,
    _dec,
    validate_student_id,
)
from gradeguard.report import export_report_csv, export_report_txt
from gradeguard.scoring import weighted_score
from gradeguard.storage import Storage

DEFAULT_DB = "gradeguard.db"


def parse_mark_pairs(mark_args: Optional[List[str]]) -> Dict[str, Decimal]:
    """Parse a list of 'Criterion=Mark' strings into a dictionary."""
    res = {}
    if not mark_args:
        return res
    for pair in mark_args:
        if "=" not in pair:
            raise GradeGuardError(
                f"Invalid mark format {pair!r}; expected 'CriterionName=MarkValue'"
            )
        k, v = pair.split("=", 1)
        k_clean = k.strip()
        if not k_clean:
            raise GradeGuardError(f"Criterion name in {pair!r} cannot be empty")
        res[k_clean] = _dec(v.strip(), f"mark for {k_clean}")
    return res


def parse_levels_input(
    levels_arg: Optional[str]
) -> Optional[List[RubricLevel]]:
    """Parse levels from a JSON file path or inline JSON string."""
    if not levels_arg:
        return None
    content = levels_arg.strip()
    if Path(content).exists() and Path(content).is_file():
        with open(content, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise GradeGuardError(f"Invalid JSON for rubric levels: {exc}")

    if not isinstance(data, list):
        raise GradeGuardError("Rubric levels JSON must be a list of level objects")

    levels = []
    for item in data:
        if not isinstance(item, dict):
            raise GradeGuardError(
                f"Each rubric level must be an object, got {item!r}"
            )
        levels.append(
            RubricLevel(
                name=item["name"],
                min_mark=item["min_mark"],
                max_mark=item["max_mark"],
                descriptor=item["descriptor"],
            )
        )
    return levels


def cmd_create_assessment(args: argparse.Namespace) -> int:
    """Create a new assessment in the database."""
    title = (args.title or "").strip()
    if not title:
        raise GradeGuardError("Assessment title cannot be empty")

    with Storage(args.db) as storage:
        existing = storage.get_assessment(title)
        if existing:
            raise GradeGuardError(f"Assessment {title!r} already exists")
        now = datetime.now(timezone.utc).isoformat()
        with storage.conn:
            storage.conn.execute(
                "INSERT INTO assessments (title, created_at) VALUES (?, ?)",
                (title, now),
            )
        print(f"Created assessment {title!r} in database {args.db}")
    return 0


def cmd_add_criterion(args: argparse.Namespace) -> int:
    """Add a criterion with weights and levels to an existing assessment."""
    with Storage(args.db) as storage:
        assessment = storage.get_assessment(args.assessment)
        if not assessment:
            cur = storage.conn.execute(
                "SELECT id FROM assessments WHERE title = ?",
                (args.assessment,),
            )
            if not cur.fetchone():
                raise GradeGuardError(
                    f"Assessment {args.assessment!r} not found in database"
                )
            assessment = Assessment(title=args.assessment, criteria=[])

        levels = parse_levels_input(args.levels)
        assessment.add_criterion(
            name=args.name,
            weight=args.weight,
            max_marks=args.max_marks,
            levels=levels,
        )

        total_weight = sum(c.weight for c in assessment.criteria)
        if total_weight > Decimal(100):
            raise GradeGuardError(
                f"Total weights exceed 100%: current total is {total_weight}%"
            )

        assessment_id = storage.conn.execute(
            "SELECT id FROM assessments WHERE title = ?",
            (args.assessment,),
        ).fetchone()["id"]

        with storage.conn:
            storage.conn.execute(
                "DELETE FROM criteria WHERE assessment_id = ?",
                (assessment_id,),
            )
            for c in assessment.criteria:
                crit_cur = storage.conn.execute(
                    """
                    INSERT INTO criteria (assessment_id, name, weight, max_marks)
                    VALUES (?, ?, ?, ?)
                    """,
                    (assessment_id, c.name, str(c.weight), str(c.max_marks)),
                )
                crit_id = crit_cur.lastrowid
                for lvl in c.levels:
                    storage.conn.execute(
                        """
                        INSERT INTO rubric_levels (
                            criterion_id, name, min_mark, max_mark, descriptor
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            crit_id,
                            lvl.name,
                            str(lvl.min_mark),
                            str(lvl.max_mark),
                            lvl.descriptor,
                        ),
                    )

        print(
            f"Added criterion {args.name!r} "
            f"(Weight: {args.weight}%, Max Marks: {args.max_marks}) "
            f"to assessment {args.assessment!r}. "
            f"Total weight: {total_weight}%/100%"
        )
    return 0


def cmd_grade(args: argparse.Namespace) -> int:
    """Grade a student anonymously, producing a DRAFT report."""
    valid_id = validate_student_id(args.student)

    marks = {}
    if args.marks:
        try:
            parsed = json.loads(args.marks)
            if not isinstance(parsed, dict):
                raise GradeGuardError(
                    "--marks must be a JSON object mapping criterion names to numbers"
                )
            marks.update({
                k: _dec(v, f"mark for {k}") for k, v in parsed.items()
            })
        except json.JSONDecodeError as exc:
            raise GradeGuardError(f"Failed to parse --marks JSON: {exc}")

    if args.mark:
        marks.update(parse_mark_pairs(args.mark))

    if not marks:
        raise GradeGuardError(
            "No marks provided. Use --marks JSON or repeated --mark Criterion=Value"
        )

    with Storage(args.db) as storage:
        assessment = storage.get_assessment(args.assessment)
        if not assessment:
            raise GradeGuardError(
                f"Assessment {args.assessment!r} not found in database"
            )

        pct, detail = weighted_score(assessment, marks)
        feedback = generate_feedback(assessment, marks)

        storage.save_score(
            assessment_title=args.assessment,
            student_id=valid_id,
            marks=marks,
            weighted_score=pct,
            feedback=feedback,
        )

        print(f"Graded student {valid_id} for assessment {args.assessment!r}:")
        print(f"Weighted Score: {pct}% [Status: DRAFT (Teacher approval required)]")
        print("Feedback:")
        for line in feedback:
            print(f"  - {line}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    """Approve a student score report for release."""
    valid_id = validate_student_id(args.student)
    teacher = (args.teacher or "Teacher").strip()

    with Storage(args.db) as storage:
        score = storage.get_score(args.assessment, valid_id)
        if not score:
            raise GradeGuardError(
                f"No score record found for student {valid_id} "
                f"in assessment {args.assessment!r}"
            )
        storage.approve_score(args.assessment, valid_id, teacher=teacher)
        print(
            f"Report for student {valid_id} in "
            f"{args.assessment!r} approved by {teacher}."
        )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export an approved student score report to .txt or .csv."""
    valid_id = validate_student_id(args.student)

    with Storage(args.db) as storage:
        assessment = storage.get_assessment(args.assessment)
        score = storage.get_score(args.assessment, valid_id)
        if not score:
            raise GradeGuardError(
                f"No score found for student {valid_id} "
                f"in assessment {args.assessment!r}"
            )

        if not score.get("is_approved"):
            raise GradeGuardError(
                f"Cannot export unapproved report for student {valid_id}. "
                "A teacher must run 'approve' before export is allowed."
            )

        fmt = args.format.lower()
        if fmt == "txt":
            content = export_report_txt(
                score, assessment=assessment, filepath=args.output
            )
        elif fmt == "csv":
            content = export_report_csv(
                score, assessment=assessment, filepath=args.output
            )
        else:
            raise GradeGuardError(
                f"Unsupported format {fmt!r}; choose 'txt' or 'csv'"
            )

        if args.output:
            print(f"Report exported to {args.output}")
        else:
            print(content)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the command line parser."""
    parser = argparse.ArgumentParser(
        prog="gradeguard",
        description="GradeGuard: Privacy-safe grading with bias guard.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-assessment
    p_create = subparsers.add_parser(
        "create-assessment", help="Create a new assessment"
    )
    p_create.add_argument(
        "--title", required=True, help="Title of the assessment"
    )
    p_create.add_argument(
        "--db", default=DEFAULT_DB, help="Path to SQLite database"
    )

    # add-criterion
    p_add = subparsers.add_parser(
        "add-criterion", help="Add a criterion to an assessment"
    )
    p_add.add_argument(
        "--assessment", required=True, help="Assessment title"
    )
    p_add.add_argument(
        "--name", required=True, help="Criterion name"
    )
    p_add.add_argument(
        "--weight", required=True, help="Percentage weight (e.g. 40)"
    )
    p_add.add_argument(
        "--max-marks", default=10, help="Max marks (default: 10)"
    )
    p_add.add_argument(
        "--levels", help="Path to JSON file or JSON string defining rubric levels"
    )
    p_add.add_argument(
        "--db", default=DEFAULT_DB, help="Path to SQLite database"
    )

    # grade
    p_grade = subparsers.add_parser(
        "grade", help="Grade a student code"
    )
    p_grade.add_argument(
        "--assessment", required=True, help="Assessment title"
    )
    p_grade.add_argument(
        "--student", required=True, help="Anonymous student code (e.g. S001)"
    )
    p_grade.add_argument(
        "--marks", help="JSON dictionary of criterion marks"
    )
    p_grade.add_argument(
        "--mark", action="append", help="Criterion=Mark pair (can repeat)"
    )
    p_grade.add_argument(
        "--db", default=DEFAULT_DB, help="Path to SQLite database"
    )

    # approve
    p_approve = subparsers.add_parser(
        "approve", help="Teacher approves draft report"
    )
    p_approve.add_argument(
        "--assessment", required=True, help="Assessment title"
    )
    p_approve.add_argument(
        "--student", required=True, help="Anonymous student code"
    )
    p_approve.add_argument(
        "--teacher", default="Teacher", help="Teacher ID/name"
    )
    p_approve.add_argument(
        "--db", default=DEFAULT_DB, help="Path to SQLite database"
    )

    # export
    p_export = subparsers.add_parser(
        "export", help="Export an approved report"
    )
    p_export.add_argument(
        "--assessment", required=True, help="Assessment title"
    )
    p_export.add_argument(
        "--student", required=True, help="Anonymous student code"
    )
    p_export.add_argument(
        "--format",
        choices=["txt", "csv"],
        default="txt",
        help="Output format",
    )
    p_export.add_argument(
        "--output", "-o", help="Target output file path"
    )
    p_export.add_argument(
        "--db", default=DEFAULT_DB, help="Path to SQLite database"
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code

    handlers = {
        "create-assessment": cmd_create_assessment,
        "add-criterion": cmd_add_criterion,
        "grade": cmd_grade,
        "approve": cmd_approve,
        "export": cmd_export,
    }

    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except GradeGuardError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
