# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [Phase P1] - 2026-10-03
### Added
- Dataset audit scripts (`tools/audit_dataset.py`, `tools/audit_dataset_deep.py`) executing A1-A11 checks.
- Audit report `reports/P1_dataset_audit.md` covering all 18 CSV files (70.4M flows).
- Gate P1 report `reports/gates/P1.md`.
- Architecture decision record in `docs/DECISIONS.md` on window classification.
### Fixed
- Resolved BLOCKER B3 by adopting the spec-compliant $\tau \ge 0.5$ tail window rule, yielding 125 benign and 106 attack windows.

## [Phase P0] - 2026-10-03
### Added
- Repository scaffold, pyproject.toml, Makefile, .pre-commit-config.yaml.
- Upstream roadmaps and TASK.md / ROADMAP.md specifications.
- FastAPI contract stub service and conformance suite.
- Synthetic stream generator (`tools/make_synthetic_stream.py`).
