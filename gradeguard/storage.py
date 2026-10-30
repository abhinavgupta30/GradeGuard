"""SQLite persistence for GradeGuard assessments, criteria, and scores.

Uses parameterised queries exclusively to completely prevent SQL injection.
Strictly stores only anonymous student codes (e.g. S001) and rubric data.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
import sqlite3
from typing import Any, Dict, List, Optional

from gradeguard.models import (
    Assessment,
    Criterion,
    GradeGuardError,
    RubricLevel,
    _dec,
    validate_student_id,
)


class Storage:
    """Manages SQLite persistence for GradeGuard with parameterised queries."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def _init_schema(self):
        """Create required tables with foreign key relationships."""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS criteria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assessment_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    weight TEXT NOT NULL,
                    max_marks TEXT NOT NULL,
                    FOREIGN KEY (assessment_id) REFERENCES assessments (id)
                        ON DELETE CASCADE,
                    UNIQUE (assessment_id, name)
                );
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rubric_levels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    criterion_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    min_mark TEXT NOT NULL,
                    max_mark TEXT NOT NULL,
                    descriptor TEXT NOT NULL,
                    FOREIGN KEY (criterion_id) REFERENCES criteria (id)
                        ON DELETE CASCADE
                );
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assessment_id INTEGER NOT NULL,
                    student_id TEXT NOT NULL,
                    weighted_score TEXT NOT NULL,
                    marks_json TEXT NOT NULL,
                    feedback_json TEXT NOT NULL,
                    is_approved INTEGER NOT NULL DEFAULT 0,
                    approved_by TEXT,
                    approved_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (assessment_id) REFERENCES assessments (id)
                        ON DELETE CASCADE,
                    UNIQUE (assessment_id, student_id)
                );
                """
            )

    def close(self):
        """Close the SQLite database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def save_assessment(self, assessment: Assessment) -> int:
        """Save assessment and its criteria with parameterised queries."""
        assessment.validate()
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            cur = self.conn.execute(
                "SELECT id FROM assessments WHERE title = ?",
                (assessment.title,),
            )
            row = cur.fetchone()
            if row:
                assessment_id = row["id"]
                self.conn.execute(
                    "DELETE FROM criteria WHERE assessment_id = ?",
                    (assessment_id,),
                )
            else:
                cur = self.conn.execute(
                    "INSERT INTO assessments (title, created_at) VALUES (?, ?)",
                    (assessment.title, now),
                )
                assessment_id = cur.lastrowid

            for c in assessment.criteria:
                crit_cur = self.conn.execute(
                    """
                    INSERT INTO criteria (assessment_id, name, weight, max_marks)
                    VALUES (?, ?, ?, ?)
                    """,
                    (assessment_id, c.name, str(c.weight), str(c.max_marks)),
                )
                crit_id = crit_cur.lastrowid
                for lvl in c.levels:
                    self.conn.execute(
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
        return assessment_id

    def get_assessment(self, title: str) -> Optional[Assessment]:
        """Load an assessment by title with all criteria and rubric levels."""
        cur = self.conn.execute(
            "SELECT id, title FROM assessments WHERE title = ?",
            (title,),
        )
        row = cur.fetchone()
        if not row:
            return None

        assessment_id = row["id"]
        crit_cur = self.conn.execute(
            """
            SELECT id, name, weight, max_marks
            FROM criteria
            WHERE assessment_id = ?
            ORDER BY id ASC
            """,
            (assessment_id,),
        )

        criteria = []
        for c_row in crit_cur.fetchall():
            c_id = c_row["id"]
            lvl_cur = self.conn.execute(
                """
                SELECT name, min_mark, max_mark, descriptor
                FROM rubric_levels
                WHERE criterion_id = ?
                ORDER BY id ASC
                """,
                (c_id,),
            )
            levels = tuple(
                RubricLevel(
                    name=l_row["name"],
                    min_mark=Decimal(l_row["min_mark"]),
                    max_mark=Decimal(l_row["max_mark"]),
                    descriptor=l_row["descriptor"],
                )
                for l_row in lvl_cur.fetchall()
            )
            criteria.append(
                Criterion(
                    name=c_row["name"],
                    weight=Decimal(c_row["weight"]),
                    max_marks=Decimal(c_row["max_marks"]),
                    levels=levels,
                )
            )

        return Assessment(title=row["title"], criteria=criteria)

    def list_assessments(self) -> List[Dict[str, Any]]:
        """List all saved assessments."""
        cur = self.conn.execute(
            """
            SELECT a.id, a.title, a.created_at, COUNT(c.id) as criterion_count
            FROM assessments a
            LEFT JOIN criteria c ON a.id = c.assessment_id
            GROUP BY a.id, a.title, a.created_at
            ORDER BY a.id ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def save_score(
        self,
        assessment_title: str,
        student_id: str,
        marks: Dict[str, object],
        weighted_score: Decimal,
        feedback: List[str],
    ) -> int:
        """Store score and feedback for an anonymous student code."""
        valid_id = validate_student_id(student_id)
        cur = self.conn.execute(
            "SELECT id FROM assessments WHERE title = ?",
            (assessment_title,),
        )
        row = cur.fetchone()
        if not row:
            raise GradeGuardError(
                f"Assessment {assessment_title!r} not found in database"
            )
        assessment_id = row["id"]

        now = datetime.now(timezone.utc).isoformat()
        marks_str = {k: str(_dec(v, f"mark for {k}")) for k, v in marks.items()}
        marks_json = json.dumps(marks_str)
        feedback_json = json.dumps(feedback)

        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO scores (
                    assessment_id, student_id, weighted_score, marks_json,
                    feedback_json, is_approved, created_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(assessment_id, student_id) DO UPDATE SET
                    weighted_score=excluded.weighted_score,
                    marks_json=excluded.marks_json,
                    feedback_json=excluded.feedback_json,
                    is_approved=0,
                    approved_by=NULL,
                    approved_at=NULL,
                    created_at=excluded.created_at
                """,
                (
                    assessment_id,
                    valid_id,
                    str(weighted_score),
                    marks_json,
                    feedback_json,
                    now,
                ),
            )
            return cur.lastrowid

    def get_score(
        self, assessment_title: str, student_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a stored score record."""
        valid_id = validate_student_id(student_id)
        cur = self.conn.execute(
            """
            SELECT s.id, a.title as assessment_title, s.student_id,
                   s.weighted_score, s.marks_json, s.feedback_json,
                   s.is_approved, s.approved_by, s.approved_at, s.created_at
            FROM scores s
            JOIN assessments a ON s.assessment_id = a.id
            WHERE a.title = ? AND s.student_id = ?
            """,
            (assessment_title, valid_id),
        )
        row = cur.fetchone()
        if not row:
            return None

        marks_raw = json.loads(row["marks_json"])
        marks = {k: Decimal(v) for k, v in marks_raw.items()}
        feedback = json.loads(row["feedback_json"])

        return {
            "id": row["id"],
            "assessment_title": row["assessment_title"],
            "student_id": row["student_id"],
            "weighted_score": Decimal(row["weighted_score"]),
            "marks": marks,
            "feedback": feedback,
            "is_approved": bool(row["is_approved"]),
            "approved_by": row["approved_by"],
            "approved_at": row["approved_at"],
            "created_at": row["created_at"],
        }

    def approve_score(
        self, assessment_title: str, student_id: str, teacher: str = "Teacher"
    ) -> bool:
        """Approve a student score report for release."""
        valid_id = validate_student_id(student_id)
        teacher_clean = (teacher or "").strip()
        if not teacher_clean:
            raise GradeGuardError("Teacher name/ID cannot be empty")

        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            cur = self.conn.execute(
                """
                UPDATE scores
                SET is_approved = 1, approved_by = ?, approved_at = ?
                WHERE student_id = ? AND assessment_id = (
                    SELECT id FROM assessments WHERE title = ?
                )
                """,
                (teacher_clean, now, valid_id, assessment_title),
            )
            return cur.rowcount > 0

    def list_scores(
        self, assessment_title: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List scores, optionally filtered by assessment title."""
        if assessment_title:
            cur = self.conn.execute(
                """
                SELECT s.id, a.title as assessment_title, s.student_id,
                       s.weighted_score, s.marks_json, s.feedback_json,
                       s.is_approved, s.approved_by, s.approved_at, s.created_at
                FROM scores s
                JOIN assessments a ON s.assessment_id = a.id
                WHERE a.title = ?
                ORDER BY s.student_id ASC
                """,
                (assessment_title,),
            )
        else:
            cur = self.conn.execute(
                """
                SELECT s.id, a.title as assessment_title, s.student_id,
                       s.weighted_score, s.marks_json, s.feedback_json,
                       s.is_approved, s.approved_by, s.approved_at, s.created_at
                FROM scores s
                JOIN assessments a ON s.assessment_id = a.id
                ORDER BY a.title ASC, s.student_id ASC
                """
            )
        results = []
        for row in cur.fetchall():
            results.append({
                "id": row["id"],
                "assessment_title": row["assessment_title"],
                "student_id": row["student_id"],
                "weighted_score": Decimal(row["weighted_score"]),
                "marks": {
                    k: Decimal(v)
                    for k, v in json.loads(row["marks_json"]).items()
                },
                "feedback": json.loads(row["feedback_json"]),
                "is_approved": bool(row["is_approved"]),
                "approved_by": row["approved_by"],
                "approved_at": row["approved_at"],
                "created_at": row["created_at"],
            })
        return results
