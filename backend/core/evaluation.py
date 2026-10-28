"""Evaluation harness for the semantic layer.

This is the Slice F check: a small, deterministic set of page fixtures that
exercise the behaviours the semantic layer promises.  It runs offline (no
portal, no model) and produces a machine-readable report:

* page type recognition,
* concept mapping for every question,
* fact status and fill-plan state for every field,
* human-only steps (OTP, CAPTCHA, payment, final submit),
* dashboard and landing paths that need a human choice,
* false-claim checks (nothing is planned for filling unless a value exists).

The harness is used by ``tests/test_evaluation.py`` and by
``scripts/evaluate_semantic_layer.py``.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .facts import FactBook
from .fill_plan import build_fill_plan
from .page_brief import build_deterministic_brief
from .perception import Perception, PerceivedAction, PerceivedField
from .vault import CandidateVault


class _VaultAdapter:
    """The fact book only needs a vault object for the evaluation run."""

    def __init__(self, vault: CandidateVault):
        self.vault = vault


@dataclass
class EvalCase:
    name: str
    perception: Perception
    expected_page_type: str
    expected_concepts: Dict[str, Optional[str]] = field(default_factory=dict)
    expected_fill_states: Dict[str, str] = field(default_factory=dict)
    expected_values: Dict[str, str] = field(default_factory=dict)
    expected_format: Dict[str, str] = field(default_factory=dict)
    expected_choice_paths: int = 0
    expect_human_only: bool = False
    expect_information: bool = False


@dataclass
class EvalCheck:
    case: str
    check: str
    passed: bool
    detail: str = ""

    def public(self) -> Dict[str, Any]:
        return {
            "case": self.case,
            "check": self.check,
            "passed": self.passed,
            "detail": self.detail,
        }


def _field(handle: str, label: str, **kwargs: Any) -> PerceivedField:
    return PerceivedField(handle=handle, label_text=label, **kwargs)


def _action(handle: str, text: str, **kwargs: Any) -> PerceivedAction:
    return PerceivedAction(handle=handle, text=text, **kwargs)


def hpsc_personal_details() -> Perception:
    """The HPSC personal-details section, including the matric-name question."""
    return Perception(
        page_signature="sha256:eval-hpsc-personal",
        url="https://regn.hpsc.gov.in/registration/personal-details",
        title="Personal Details",
        fields=[
            _field("fp-1", "First Name", group_heading="Personal Details", required=True),
            _field("fp-2", "Middle Name", group_heading="Personal Details"),
            _field("fp-3", "Last Name", group_heading="Personal Details", required=True),
            _field(
                "fp-4",
                "Date of Birth",
                placeholder="DD-MM-YYYY",
                group_heading="Personal Details",
                required=True,
            ),
            _field(
                "fp-5",
                "Name as printed on matric certificate",
                group_heading="Personal Details",
                required=True,
            ),
            _field("fp-6", "Father's Name", group_heading="Personal Details", required=True),
            _field("fp-7", "Email Address", group_heading="Contact Details", required=True),
            _field("fp-8", "Confirm Email", group_heading="Contact Details", required=True),
            _field("fp-9", "Mobile Number", group_heading="Contact Details", required=True),
            _field(
                "fp-10",
                "Upload Photograph",
                input_type="file",
                group_heading="Documents",
                required=True,
            ),
        ],
        actions=[
            _action("fp-11", "Save & Next", kind_hint="next", role="button"),
        ],
        visible_text="Personal Details. Fields marked * are required.",
    )


def hpsc_otp() -> Perception:
    return Perception(
        page_signature="sha256:eval-hpsc-otp",
        url="https://regn.hpsc.gov.in/registration/otp",
        title="Verify your mobile number",
        fields=[_field("fp-1", "Enter OTP", required=True)],
        actions=[_action("fp-2", "Verify", role="button")],
        visible_text="A one-time password was sent to your mobile number.",
        signals={"otp": True},
    )


def hpsc_dashboard() -> Perception:
    return Perception(
        page_signature="sha256:eval-hpsc-dashboard",
        url="https://regn.hpsc.gov.in/dashboard",
        title="Candidate Dashboard",
        visible_text=(
            "Welcome Aman Kumar Sharma. Application status: Submitted. "
            "Registration ID: HPSC-2026-000123"
        ),
        actions=[
            _action("fp-1", "View Application Preview", role="link"),
            _action("fp-2", "Proceed for Universal Registration", kind_hint="next", role="button"),
            _action("fp-3", "Logout", role="link"),
        ],
    )


def hpsc_landing() -> Perception:
    return Perception(
        page_signature="sha256:eval-hpsc-landing",
        url="https://regn.hpsc.gov.in/",
        title="HPSC Universal Registration",
        visible_text="New candidates register. Existing candidates sign in to continue.",
        actions=[
            _action("fp-1", "Register", kind_hint="register", role="link"),
            _action("fp-2", "Login", kind_hint="login", role="link"),
        ],
    )


def expired_session() -> Perception:
    return Perception(
        page_signature="sha256:eval-error",
        url="https://regn.hpsc.gov.in/registration/error",
        title="Session Expired",
        visible_text="Your session has expired. Please log in again.",
    )


def cases() -> List[EvalCase]:
    return [
        EvalCase(
            name="hpsc_personal_details",
            perception=hpsc_personal_details(),
            expected_page_type="SECTION_FORM",
            expected_concepts={
                "fp-1": "first_name",
                "fp-2": "middle_name",
                "fp-3": "last_name",
                "fp-4": "date_of_birth",
                "fp-5": "name_as_matric",
                "fp-6": "father_name",
                "fp-7": "email",
                "fp-8": "confirm_email",
                "fp-9": "mobile",
                "fp-10": "photo_upload",
            },
            expected_fill_states={
                "fp-1": "fill",
                "fp-2": "fill",
                "fp-3": "fill",
                "fp-4": "fill",
                "fp-5": "confirm",
                "fp-6": "fill",
                "fp-7": "fill",
                "fp-8": "fill",
                "fp-9": "fill",
                "fp-10": "upload",
            },
            expected_values={
                "fp-1": "Aman",
                "fp-2": "Kumar",
                "fp-3": "Sharma",
                "fp-4": "15-08-2003",
            },
            expected_format={"fp-4": "DD-MM-YYYY"},
        ),
        EvalCase(
            name="hpsc_otp",
            perception=hpsc_otp(),
            expected_page_type="OTP",
            expected_concepts={"fp-1": None},
            expected_fill_states={"fp-1": "human_only"},
            expect_human_only=True,
        ),
        EvalCase(
            name="hpsc_dashboard",
            perception=hpsc_dashboard(),
            expected_page_type="DASHBOARD",
            expected_choice_paths=2,
            expect_information=True,
        ),
        EvalCase(
            name="hpsc_landing",
            perception=hpsc_landing(),
            expected_page_type="LANDING",
            expected_choice_paths=2,
        ),
        EvalCase(
            name="expired_session",
            perception=expired_session(),
            expected_page_type="ERROR",
        ),
    ]


def _check(case: str, check: str, passed: bool, detail: str = "") -> EvalCheck:
    return EvalCheck(case=case, check=check, passed=bool(passed), detail=detail)


def _case_checks(
    case: EvalCase,
    brief: Any,
    plan: Dict[str, Any],
) -> List[EvalCheck]:
    checks: List[EvalCheck] = [
        _check(
            case.name,
            "page_type",
            brief.page_type == case.expected_page_type,
            f"expected {case.expected_page_type}, got {brief.page_type}",
        )
    ]

    questions = {question.handle: question for question in brief.questions}
    for handle, expected_concept in case.expected_concepts.items():
        question = questions.get(handle)
        actual = question.concept if question else "<missing>"
        checks.append(
            _check(
                case.name,
                f"concept:{handle}",
                actual == expected_concept,
                f"expected {expected_concept}, got {actual}",
            )
        )

    for handle, expected_state in case.expected_fill_states.items():
        instruction = plan.get(handle)
        actual = instruction.state if instruction else "<missing>"
        checks.append(
            _check(
                case.name,
                f"fill_state:{handle}",
                actual == expected_state,
                f"expected {expected_state}, got {actual}",
            )
        )

    for handle, expected_value in case.expected_values.items():
        instruction = plan.get(handle)
        actual = instruction.value if instruction else None
        checks.append(
            _check(
                case.name,
                f"value:{handle}",
                actual == expected_value,
                f"expected {expected_value!r}, got {actual!r}",
            )
        )

    for handle, expected_format in case.expected_format.items():
        question = questions.get(handle)
        actual = question.expected_format if question else None
        checks.append(
            _check(
                case.name,
                f"format:{handle}",
                actual == expected_format,
                f"expected {expected_format}, got {actual}",
            )
        )

    choice_paths = [path for path in brief.paths if path.needs_human_choice]
    checks.append(
        _check(
            case.name,
            "choice_paths",
            len(choice_paths) == case.expected_choice_paths,
            f"expected {case.expected_choice_paths}, got {len(choice_paths)}",
        )
    )

    if case.expect_human_only:
        checks.append(
            _check(
                case.name,
                "human_only",
                any(question.human_only for question in brief.questions)
                and "otp" in brief.human_only,
                f"human_only={brief.human_only}",
            )
        )
    if case.expect_information:
        checks.append(
            _check(
                case.name,
                "information",
                any(item.kind == "identifier" for item in brief.information),
                f"information={[item.label for item in brief.information]}",
            )
        )

    # False-claim checks: a plan may only promise a value it actually has, and
    # a human-only step must never carry a value.
    for handle, instruction in plan.items():
        if instruction.state == "fill":
            checks.append(
                _check(
                    case.name,
                    f"false_claim:{handle}",
                    bool(instruction.value),
                    "a fill instruction must carry a value",
                )
            )
        if instruction.state in {"human_only", "ask_human", "confirm"}:
            checks.append(
                _check(
                    case.name,
                    f"no_silent_value:{handle}",
                    instruction.state != "human_only" or instruction.value in (None, ""),
                    "a human-only step must not carry a value",
                )
            )
    return checks


def run_evaluation(
    *,
    vault: Optional[CandidateVault] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run every fixture and return a report.  No network, no model calls."""
    profile = vault or CandidateVault()
    tmp = tempfile.TemporaryDirectory(prefix="formpilot-eval-")
    try:
        book = FactBook(
            str(Path(tmp.name) / "facts.json"),
            vault_manager=_VaultAdapter(profile),
        )
        checks: List[EvalCheck] = []
        case_reports: List[Dict[str, Any]] = []
        concept_total = 0
        concept_passed = 0
        state_total = 0
        state_passed = 0

        for case in cases():
            brief = build_deterministic_brief(case.perception)
            book.annotate_brief(brief, domain="regn.hpsc.gov.in", vault=profile)
            plan = build_fill_plan(
                case.perception,
                book,
                vault=profile,
                domain="regn.hpsc.gov.in",
            )
            case_checks = _case_checks(case, brief, plan)
            checks.extend(case_checks)
            for check in case_checks:
                if check.check.startswith("concept:"):
                    concept_total += 1
                    concept_passed += int(check.passed)
                if check.check.startswith("fill_state:"):
                    state_total += 1
                    state_passed += int(check.passed)
            case_reports.append(
                {
                    "name": case.name,
                    "page_type": brief.page_type,
                    "questions": len(brief.questions),
                    "paths": len(brief.paths),
                    "checks": [check.public() for check in case_checks],
                }
            )

        failed = [check for check in checks if not check.passed]
        return {
            "passed": not failed,
            "metrics": {
                "cases": len(case_reports),
                "checks": len(checks),
                "passed": len(checks) - len(failed),
                "failed": len(failed),
                "concept_accuracy": round(concept_passed / concept_total, 3)
                if concept_total
                else 1.0,
                "fill_state_accuracy": round(state_passed / state_total, 3)
                if state_total
                else 1.0,
            },
            "failures": [check.public() for check in failed],
            "cases": case_reports,
        }
    finally:
        tmp.cleanup()


def format_report(report: Dict[str, Any]) -> str:
    """A short human-readable summary for the CLI and the test output."""
    metrics = report["metrics"]
    lines = [
        "Semantic layer evaluation",
        f"  cases: {metrics['cases']}  checks: {metrics['checks']}  "
        f"passed: {metrics['passed']}  failed: {metrics['failed']}",
        f"  concept accuracy: {metrics['concept_accuracy']:.1%}",
        f"  fill-state accuracy: {metrics['fill_state_accuracy']:.1%}",
    ]
    if report["failures"]:
        lines.append("  failures:")
        for failure in report["failures"]:
            lines.append(
                f"    - {failure['case']} / {failure['check']}: {failure['detail']}"
            )
    else:
        lines.append("  result: PASS")
    return "\n".join(lines)
