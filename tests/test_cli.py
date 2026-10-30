"""Unit tests for GradeGuard command-line interface (CLI)."""
from pathlib import Path

from gradeguard.cli import main


def test_cli_end_to_end_workflow(tmp_path, capsys):
    db_file = str(tmp_path / "test_cli.db")

    # 1. create-assessment
    exit_code = main([
        "create-assessment", "--title", "Final Project", "--db", db_file
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Created assessment 'Final Project'" in captured.out

    # 2. add criteria
    exit_code = main([
        "add-criterion", "--assessment", "Final Project",
        "--name", "Architecture", "--weight", "60", "--max-marks", "10",
        "--db", db_file
    ])
    assert exit_code == 0

    exit_code = main([
        "add-criterion", "--assessment", "Final Project",
        "--name", "Testing", "--weight", "40", "--max-marks", "10",
        "--db", db_file
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Total weight: 100%/100%" in captured.out

    # 3. grade student
    exit_code = main([
        "grade", "--assessment", "Final Project",
        "--student", "S999",
        "--mark", "Architecture=9",
        "--mark", "Testing=8",
        "--db", db_file
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Weighted Score: 86.00%" in captured.out
    assert "DRAFT" in captured.out

    # 4. attempt export before approval: must fail with exit code 1
    export_txt = str(tmp_path / "report_S999.txt")
    exit_code = main([
        "export", "--assessment", "Final Project",
        "--student", "S999",
        "--format", "txt",
        "--output", export_txt,
        "--db", db_file
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "A teacher must run 'approve' before export is allowed" in captured.err

    # 5. approve report
    exit_code = main([
        "approve", "--assessment", "Final Project",
        "--student", "S999",
        "--teacher", "Dr. Alan Turing",
        "--db", db_file
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "approved by Dr. Alan Turing" in captured.out

    # 6. export approved report to txt
    exit_code = main([
        "export", "--assessment", "Final Project",
        "--student", "S999",
        "--format", "txt",
        "--output", export_txt,
        "--db", db_file
    ])
    assert exit_code == 0
    assert Path(export_txt).exists()
    content_txt = Path(export_txt).read_text(encoding="utf-8")
    assert "APPROVED by Dr. Alan Turing" in content_txt
    assert "Weighted Score: 86.00%" in content_txt

    # 7. export approved report to csv
    export_csv = str(tmp_path / "report_S999.csv")
    exit_code = main([
        "export", "--assessment", "Final Project",
        "--student", "S999",
        "--format", "csv",
        "--output", export_csv,
        "--db", db_file
    ])
    assert exit_code == 0
    assert Path(export_csv).exists()
    content_csv = Path(export_csv).read_text(encoding="utf-8")
    assert "S999,Final Project,86.00,APPROVED,Dr. Alan Turing" in content_csv


def test_cli_grade_with_json_marks(tmp_path, capsys):
    db_file = str(tmp_path / "test_json.db")
    main(["create-assessment", "--title", "Midterm", "--db", db_file])
    main([
        "add-criterion", "--assessment", "Midterm",
        "--name", "Exam", "--weight", "100", "--max-marks", "100",
        "--db", db_file
    ])

    exit_code = main([
        "grade", "--assessment", "Midterm",
        "--student", "S100",
        "--marks", '{"Exam": 92}',
        "--db", db_file
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Weighted Score: 92.00%" in captured.out


def test_cli_rejects_privacy_violations(tmp_path, capsys):
    db_file = str(tmp_path / "test_privacy.db")
    main(["create-assessment", "--title", "Quiz", "--db", db_file])
    main([
        "add-criterion", "--assessment", "Quiz",
        "--name", "Q1", "--weight", "100", "--max-marks", "10",
        "--db", db_file
    ])

    # Real student name rejected
    exit_code = main([
        "grade", "--assessment", "Quiz",
        "--student", "John Smith",
        "--mark", "Q1=10",
        "--db", db_file
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "appears to be a real name" in captured.err


def test_cli_error_handling_and_validation(tmp_path, capsys):
    db_file = str(tmp_path / "test_errors.db")

    # 1. create-assessment with empty title
    exit_code = main(["create-assessment", "--title", "   ", "--db", db_file])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Assessment title cannot be empty" in captured.err

    # 2. create assessment validly
    main(["create-assessment", "--title", "Physics", "--db", db_file])
    # Duplicate creation
    exit_code = main(["create-assessment", "--title", "Physics", "--db", db_file])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "already exists" in captured.err

    # 3. add-criterion to non-existent assessment
    exit_code = main([
        "add-criterion", "--assessment", "NonExistent",
        "--name", "C1", "--weight", "50", "--db", db_file
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "not found in database" in captured.err

    # 4. add-criterion with custom levels JSON
    levels_json = (
        '[{"name": "Low", "min_mark": 0, "max_mark": 5, '
        '"descriptor": "Low attempt."}, '
        '{"name": "High", "min_mark": 5.1, "max_mark": 10, '
        '"descriptor": "High attempt."}]'
    )
    exit_code = main([
        "add-criterion", "--assessment", "Physics",
        "--name", "Theory", "--weight", "60", "--levels", levels_json,
        "--db", db_file
    ])
    assert exit_code == 0

    # 5. add-criterion exceeding 100%
    exit_code = main([
        "add-criterion", "--assessment", "Physics",
        "--name", "Lab", "--weight", "50", "--db", db_file
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Total weights exceed 100%" in captured.err

    # 6. grade without marks
    exit_code = main([
        "grade", "--assessment", "Physics",
        "--student", "S001", "--db", db_file
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No marks provided" in captured.err

    # 7. grade with malformed mark pair
    exit_code = main([
        "grade", "--assessment", "Physics",
        "--student", "S001", "--mark", "BadPairNoEquals", "--db", db_file
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Invalid mark format" in captured.err

    # 8. approve non-existent report
    exit_code = main([
        "approve", "--assessment", "Physics",
        "--student", "S999", "--db", db_file
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No score record found" in captured.err

    # 9. export non-existent report
    exit_code = main([
        "export", "--assessment", "Physics",
        "--student", "S999", "--db", db_file
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No score found for student" in captured.err
