# Changelog

All notable changes to the GradeGuard project are documented in this file.

## [1.0.0] - 2026-10-30

### Added
- **Modular Package Structure**: Converted the single-file prototype into a clean package under `gradeguard/` containing:
  - `models.py`: Domain models (`Assessment`, `Criterion`, `RubricLevel`, `Report`, `GradeGuardError`), exact Decimal conversion, and anonymous student ID validation.
  - `scoring.py`: Exact Decimal arithmetic and single-step `ROUND_HALF_UP` rounding.
  - `feedback.py`: Rubric-based deterministic feedback generator with a `BiasGuard` inspection system.
  - `storage.py`: SQLite persistence layer using exclusively parameterized queries (`?`) for SQL injection defense.
  - `report.py`: Report formatting, approval gating, and export routines for `.txt` and `.csv`.
  - `cli.py`: Production-ready `argparse` CLI supporting subcommands: `create-assessment`, `add-criterion`, `grade`, `approve`, and `export`.
  - `__main__.py`: Entry point for `python -m gradeguard`.
- **Rubric Levels Support**: Criteria now support multi-tier rubric levels (e.g., Excellent, Good, Basic, Poor) with defined mark ranges (`min_mark` to `max_mark`) and objective descriptor text.
- **Bias Guard Protection**: Automated verification engine rejecting feedback lines containing personal remarks, gendered words, or real names. Proven determinism: identical marks always produce identical feedback.
- **Privacy Enforcement**: Strict validation rejecting student names, real-name patterns, and raw student work text. Only anonymous identifiers (e.g., `S001`) are accepted and stored.
- **Teacher Approval Workflow**: Scored reports are created in `DRAFT` status. The system strictly blocks `.txt` and `.csv` exports until a teacher explicitly calls `approve()`.
- **Export Capabilities**: Approved reports can be exported to formatted text files (`.txt`) and structured tabular data (`.csv`).
- **Comprehensive Test Suite**: Expanded test suite to 43 unit tests (surpassing the 25-test requirement), achieving 92% code coverage. Tests verify exact `33.3 + 33.3 + 33.4` weight sums, `.xx5` half-up rounding boundaries, SQL injection attempts, approval constraints, and CLI execution flows.
- **Code Quality & Security Reports**: Configured `.flake8` and `bandit`. Zero PEP 8 violations and zero security vulnerabilities documented in `docs/quality_report.txt`.
- **Acceptance Criteria Matrix**: Added `docs/ACCEPTANCE.md` tracing all project requirements to verifying test cases.

### Changed
- Preserved all original prototype public signatures (`Assessment.add_criterion`, `Assessment.validate`, `weighted_score`, `score_report`), ensuring all 10 legacy tests pass without modification.
- Extracted dev tooling into `requirements-dev.txt` (`pytest`, `pytest-cov`, `flake8`, `bandit`) while keeping core runtime dependencies standard-library-only.
- Replaced the single-file `gradeguard.py` with the `gradeguard` package, keeping a backwards-compatible stub in `gradeguard/gradeguard.py`.

### Fixed
- Fixed leading/trailing space bug in student ID privacy checks by stripping whitespace before verifying character patterns.
- Fixed length check ordering in `validate_student_id` so student essay text is specifically flagged as exceeding character limits rather than misidentified as a personal name.
- Fixed CSV output escaping in export verification for descriptors containing commas.
