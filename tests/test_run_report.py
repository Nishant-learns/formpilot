"""The plain-language run report and the run page."""

from __future__ import annotations

import shutil

from backend.core.run_report import build_run_report, render_run_report_html
from backend.core.run_store import RunStore


def _store(tmp_path) -> RunStore:
    return RunStore(tmp_path / "runs")


def _base_run(store: RunStore, run_id: str = "run-report") -> None:
    store.start(run_id, {"query": "hpsc", "run_mode": "fill"})
    store.record_step(run_id, "run", output={"query": "hpsc", "run_mode": "fill"})
    store.record_step(
        run_id,
        "perceive",
        output={"page_type": "form", "field_count": 4, "confidence": 0.9},
    )
    store.record_step(
        run_id,
        "fill",
        output={
            "attempted": 4,
            "verified": 3,
            "failed": 1,
            "skipped": 0,
            "reformatted": 1,
            "retried": 1,
            "section": 1,
        },
    )
    store.record_step(run_id, "advance", output={"url": "https://portal.example/step-2"})


def _report(tmp_path, run_id: str = "run-report"):
    store = _store(tmp_path)
    return store, build_run_report(store.run_detail(run_id))


def test_a_payment_run_tells_the_human_to_pay(tmp_path):
    store = _store(tmp_path)
    _base_run(store)
    store.record_step(
        "run-report",
        "submit",
        status="waiting",
        output={"final_action": False, "gate_type": "PRE_PAYMENT_SAFETY_LOCK"},
    )
    store.save_audit(
        "run-report",
        {
            "total_checked": 4,
            "total_matched": 3,
            "total_mismatches": 1,
            "values_masked": True,
            "audit_hash": "abc123",
        },
    )
    store.finish(
        "run-report",
        "AWAITING_PAYMENT",
        {
            "target_url": "https://portal.example/pay",
            "run_clock": {"active_seconds": 40.0, "attended_seconds": 12.0, "wall_seconds": 52.0},
        },
    )

    report = build_run_report(store.run_detail("run-report"))

    assert report["state_label"] == "Ready for your review"
    assert report["what_to_do_now"]["title"] == "Complete the payment yourself"
    assert "payment" in report["what_to_do_now"]["detail"].lower()
    assert report["stats"]["fields_verified"] == 3
    assert report["stats"]["fields_attempted"] == 4
    assert report["stats"]["attended_seconds"] == 12.0
    assert report["audit"]["matched"] == 3
    assert report["audit"]["values_masked"] is True
    assert any("3 of 4" in line for line in report["what_happened"])


def test_a_final_submission_run_tells_the_human_to_submit(tmp_path):
    store = _store(tmp_path)
    _base_run(store)
    store.record_step(
        "run-report",
        "submit",
        status="waiting",
        output={"final_action": True, "gate_type": "PRE_PAYMENT_SAFETY_LOCK"},
    )
    store.finish("run-report", "AWAITING_PAYMENT")

    report = build_run_report(store.run_detail("run-report"))

    assert report["what_to_do_now"]["title"] == "Complete the final submission yourself"


def test_an_invalidated_review_is_explained(tmp_path):
    store = _store(tmp_path)
    _base_run(store)
    store.record_step(
        "run-report",
        "submit",
        status="invalidated",
        output={"final_action": False, "reason": "fields_changed"},
    )
    store.finish("run-report", "AWAITING_PAYMENT")

    report = build_run_report(store.run_detail("run-report"))

    assert report["what_to_do_now"]["title"] == "Review the form again"
    assert "changed" in report["what_to_do_now"]["detail"].lower()
    assert any("no longer valid" in item["detail"] for item in report["timeline"])


def test_a_failed_run_shows_the_failure_and_retryability(tmp_path):
    store = _store(tmp_path)
    _base_run(store)
    store.record_step(
        "run-report",
        "error",
        status="failed",
        error_code="navigation_failure",
        output={"message": "The portal did not move to the next step."},
    )
    store.finish(
        "run-report",
        "FAILED",
        {"error": "The portal did not move to the next step."},
    )

    report = build_run_report(store.run_detail("run-report"))

    assert report["failure"]["code"] == "navigation_failure"
    assert report["failure"]["retryable"] is True
    assert report["what_to_do_now"]["kind"] == "error"
    assert "try again" in report["what_to_do_now"]["detail"].lower()


def test_waiting_gate_tells_the_human_what_to_answer(tmp_path):
    store = _store(tmp_path)
    _base_run(store)
    store.record_step(
        "run-report",
        "gate",
        status="waiting",
        output={"gate_type": "OTP_RELAY", "title": "Enter the one-time code"},
    )
    store.finish("run-report", "WAITING_FOR_USER")

    report = build_run_report(store.run_detail("run-report"))

    assert report["what_to_do_now"]["title"] == "Answer the checkpoint"
    assert "Enter the one-time code" in report["what_to_do_now"]["detail"]


def test_the_timeline_is_plain_language(tmp_path):
    store = _store(tmp_path)
    _base_run(store)
    store.finish("run-report", "DONE")

    report = build_run_report(store.run_detail("run-report"))

    labels = [item["label"] for item in report["timeline"]]
    assert labels == ["Run", "Read the page", "Filled fields", "Moved forward"]
    fill = report["timeline"][2]
    assert "Verified 3 of 4 fields" in fill["detail"]
    assert fill["anchor"] == "#step-3"


def test_the_html_page_is_escaped_and_contains_the_action(tmp_path):
    store = _store(tmp_path)
    _base_run(store)
    store.append("run-report", {"phase": "SENSE", "message": "<script>alert(1)</script>"})
    store.finish("run-report", "AWAITING_PAYMENT")
    report = build_run_report(store.run_detail("run-report"))

    page = render_run_report_html(report)

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(1)</script>" not in page
    assert "Complete the payment yourself" in page
    assert "What happened" in page
    assert "FormPilot never solves a CAPTCHA" in page


# ---------------------------------------------------------------------- API


def test_the_report_api_and_html_page(client, tmp_path):
    from backend.main import run_store

    run_id = "api-report-run"
    try:
        _base_run(run_store, run_id)
        run_store.finish(run_id, "AWAITING_PAYMENT")

        response = client.get(f"/api/runs/{run_id}/report")
        assert response.status_code == 200
        payload = response.json()
        assert payload["run_id"] == run_id
        assert payload["what_to_do_now"]["title"] == "Complete the payment yourself"
        assert payload["timeline"]

        page = client.get(f"/runs/{run_id}")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert "What happened" in page.text
    finally:
        shutil.rmtree(run_store.root / run_id, ignore_errors=True)


def test_a_missing_run_has_no_report(client):
    assert client.get("/api/runs/not-a-real-run/report").status_code == 404
    assert client.get("/runs/not-a-real-run").status_code == 404


# ------------------------------------------------- runs without a step ledger


def test_an_older_run_still_gets_a_timeline_from_its_events(tmp_path):
    store = _store(tmp_path)
    store.start("run-old", {"query": "hpsc", "run_mode": "fill"})
    store.append(
        "run-old",
        {"phase": "SENSE", "message": "Reading the page: 1 fields found.", "gate_type": None},
    )
    store.append(
        "run-old",
        {
            "phase": "DECIDE",
            "message": "Waiting for you to choose a sign-in method.",
            "gate_type": "LOGIN_METHOD",
        },
    )
    store.finish("run-old", "WAITING_FOR_USER")

    report = build_run_report(store.run_detail("run-old"))

    assert [item["label"] for item in report["timeline"]] == [
        "Read the page",
        "Stopped for you",
    ]
    assert report["what_to_do_now"]["title"] == "Answer the checkpoint"
    assert "sign-in method" in report["what_to_do_now"]["detail"]
