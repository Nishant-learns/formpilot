"""Slice F: the semantic layer's evaluation fixtures must all pass."""

from __future__ import annotations

from backend.core.evaluation import (
    cases,
    format_report,
    hpsc_dashboard,
    hpsc_landing,
    hpsc_otp,
    hpsc_personal_details,
    run_evaluation,
)


def test_semantic_layer_evaluation_passes_every_check():
    report = run_evaluation()

    assert report["passed"] is True, format_report(report)
    assert report["failures"] == []
    assert report["metrics"]["cases"] == len(cases())
    assert report["metrics"]["concept_accuracy"] == 1.0
    assert report["metrics"]["fill_state_accuracy"] == 1.0
    assert "PASS" in format_report(report)


def test_hpsc_dates_are_understood_as_dates_in_the_page_format():
    report = run_evaluation()
    personal = next(
        item for item in report["cases"] if item["name"] == "hpsc_personal_details"
    )
    checks = {check["check"]: check for check in personal["checks"]}

    assert checks["format:fp-4"]["passed"] is True
    assert checks["value:fp-4"]["passed"] is True


def test_hpsc_name_parts_fill_and_matric_name_asks_once():
    report = run_evaluation()
    personal = next(
        item for item in report["cases"] if item["name"] == "hpsc_personal_details"
    )
    checks = {check["check"]: check for check in personal["checks"]}

    assert checks["fill_state:fp-1"]["passed"] is True
    assert checks["fill_state:fp-2"]["passed"] is True
    assert checks["fill_state:fp-3"]["passed"] is True
    assert checks["fill_state:fp-5"]["passed"] is True


def test_otp_is_human_only_and_never_planned_as_a_fill():
    from backend.core.facts import FactBook
    from backend.core.fill_plan import build_fill_plan
    from backend.core.vault import CandidateVault

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        class Manager:
            vault = CandidateVault()

        book = FactBook(str(Path(tmp) / "facts.json"), vault_manager=Manager())
        plan = build_fill_plan(hpsc_otp(), book, vault=CandidateVault())

    assert plan["fp-1"].state == "human_only"
    assert plan["fp-1"].value is None


def test_dashboard_and_landing_paths_ask_the_human_to_choose():
    from backend.core.page_brief import build_deterministic_brief

    dashboard = build_deterministic_brief(hpsc_dashboard())
    landing = build_deterministic_brief(hpsc_landing())

    dashboard_choices = [path.label for path in dashboard.paths if path.needs_human_choice]
    landing_choices = [path.label for path in landing.paths if path.needs_human_choice]

    assert "Proceed for Universal Registration" in dashboard_choices
    assert "View Application Preview" in dashboard_choices
    assert set(landing_choices) == {"Register", "Login"}


def test_personal_details_page_is_a_section_form_with_a_save_and_next_path():
    from backend.core.page_brief import build_deterministic_brief

    brief = build_deterministic_brief(hpsc_personal_details())

    assert brief.page_type == "SECTION_FORM"
    assert any(path.label == "Save & Next" for path in brief.paths)
    assert brief.question_count() == 10
