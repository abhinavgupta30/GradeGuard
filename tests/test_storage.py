"""Unit tests for SQLite storage, approval tracking, and SQL-injection defense."""
from decimal import Decimal
import pytest

from gradeguard.models import Assessment, GradeGuardError, RubricLevel
from gradeguard.storage import Storage


def test_storage_save_and_retrieve_assessment():
    with Storage(":memory:") as storage:
        a = Assessment("Physics Exam")
        custom_levels = [
            RubricLevel("Poor", Decimal("0"), Decimal("4"), "Needs work."),
            RubricLevel("Good", Decimal("4.1"), Decimal("10"), "Good work."),
        ]
        a.add_criterion("Mechanics", 60, 10, levels=custom_levels)
        a.add_criterion("Optics", 40, 10)

        storage.save_assessment(a)
        retrieved = storage.get_assessment("Physics Exam")

        assert retrieved is not None
        assert retrieved.title == "Physics Exam"
        assert len(retrieved.criteria) == 2
        assert retrieved.criteria[0].name == "Mechanics"
        assert retrieved.criteria[0].weight == Decimal("60")
        assert len(retrieved.criteria[0].levels) == 2
        assert retrieved.criteria[1].name == "Optics"
        assert retrieved.criteria[1].weight == Decimal("40")


def test_storage_save_and_approve_score():
    with Storage(":memory:") as storage:
        a = Assessment("Chemistry Test")
        a.add_criterion("Lab", 100, 10)
        storage.save_assessment(a)

        # Save initial score: must start in DRAFT
        storage.save_score(
            assessment_title="Chemistry Test",
            student_id="S001",
            marks={"Lab": Decimal("8.5")},
            weighted_score=Decimal("85.00"),
            feedback=["Lab: strong work, keep it up."],
        )

        record = storage.get_score("Chemistry Test", "S001")
        assert record is not None
        assert record["student_id"] == "S001"
        assert record["weighted_score"] == Decimal("85.00")
        assert record["is_approved"] is False
        assert record["approved_by"] is None

        # Approve score
        success = storage.approve_score(
            "Chemistry Test", "S001", teacher="Prof. Curie"
        )
        assert success is True

        updated = storage.get_score("Chemistry Test", "S001")
        assert updated["is_approved"] is True
        assert updated["approved_by"] == "Prof. Curie"
        assert updated["approved_at"] is not None


def test_storage_privacy_rejects_student_names():
    with Storage(":memory:") as storage:
        a = Assessment("Quiz")
        a.add_criterion("Q1", 100, 10)
        storage.save_assessment(a)

        with pytest.raises(GradeGuardError, match="appears to be a real name"):
            storage.save_score(
                assessment_title="Quiz",
                student_id="John Smith",
                marks={"Q1": Decimal("10")},
                weighted_score=Decimal("100.00"),
                feedback=["Q1: strong work"],
            )


def test_sql_injection_defense():
    """Verify that SQLite storage is completely immune to SQL injection."""
    with Storage(":memory:") as storage:
        # 1. SQL injection in assessment title
        malicious_title = "Math'); DROP TABLE assessments;--"
        a = Assessment(malicious_title)
        a.add_criterion("Algebra", 100, 10)
        storage.save_assessment(a)

        # Verify table was NOT dropped
        cur = storage.conn.execute("SELECT count(*) as count FROM assessments")
        assert cur.fetchone()["count"] == 1

        # Verify assessment is retrieved literally by exact title
        loaded = storage.get_assessment(malicious_title)
        assert loaded is not None
        assert loaded.title == malicious_title

        # 2. SQL injection in student ID (rejected by privacy validation)
        with pytest.raises(GradeGuardError):
            storage.save_score(
                assessment_title=malicious_title,
                student_id="' OR '1'='1",
                marks={"Algebra": Decimal("8")},
                weighted_score=Decimal("80.00"),
                feedback=["Algebra: strong work"],
            )

        # 3. Parameterized query ensures safe literal storage
        safe_injection_attempt_id = "ANON_INJECT_1"
        storage.save_score(
            assessment_title=malicious_title,
            student_id=safe_injection_attempt_id,
            marks={"Algebra": Decimal("8")},
            weighted_score=Decimal("80.00"),
            feedback=["Algebra: strong work"],
        )
        score_record = storage.get_score(
            malicious_title, safe_injection_attempt_id
        )
        assert score_record is not None
        assert score_record["student_id"] == safe_injection_attempt_id

        # 4. Criteria table was not dropped
        crit_cur = storage.conn.execute("SELECT count(*) as count FROM criteria")
        assert crit_cur.fetchone()["count"] >= 1


def test_storage_listing_and_edge_cases():
    with Storage(":memory:") as storage:
        # List empty
        assert storage.list_assessments() == []
        assert storage.list_scores() == []

        a = Assessment("Biology")
        a.add_criterion("Cell", 100, 10)
        storage.save_assessment(a)

        assessments = storage.list_assessments()
        assert len(assessments) == 1
        assert assessments[0]["title"] == "Biology"
        assert assessments[0]["criterion_count"] == 1

        # Save score for non-existent assessment raises GradeGuardError
        with pytest.raises(GradeGuardError, match="not found in database"):
            storage.save_score(
                "NonExistent", "S001", {"Cell": 10}, Decimal("100"), ["fb"]
            )

        # Save valid score
        storage.save_score(
            "Biology", "S001", {"Cell": 10}, Decimal("100"), ["feedback"]
        )
        # Update existing score
        storage.save_score(
            "Biology", "S001", {"Cell": 9}, Decimal("90"), ["new feedback"]
        )

        scores_all = storage.list_scores()
        assert len(scores_all) == 1
        assert scores_all[0]["weighted_score"] == Decimal("90")

        scores_filtered = storage.list_scores("Biology")
        assert len(scores_filtered) == 1

        # Approve with empty teacher
        with pytest.raises(GradeGuardError, match="Teacher name/ID cannot be empty"):
            storage.approve_score("Biology", "S001", teacher="  ")

        # Approve non-existent student returns False
        assert storage.approve_score(
            "Biology", "S999", teacher="Teacher"
        ) is False

        # Get non-existent score returns None
        assert storage.get_score("Biology", "S999") is None

        # Get non-existent assessment returns None
        assert storage.get_assessment("NonExistent") is None
