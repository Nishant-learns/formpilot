"""Deterministic and model-assisted page brief tests."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from backend.core.page_brief import (
    PageBriefCache,
    PageInterpreter,
    build_deterministic_brief,
    classify_page,
)
from backend.core.perception import Perception, PerceivedAction, PerceivedField


def _field(
    handle: str,
    label: str,
    *,
    placeholder: str = "",
    helper: str = "",
    group: str = "",
    input_type: str = "text",
    tag: str = "input",
    required: bool = False,
) -> PerceivedField:
    return PerceivedField(
        handle=handle,
        label_text=label,
        placeholder=placeholder,
        helper_text=helper,
        group_heading=group,
        input_type=input_type,
        tag=tag,
        required=required,
    )


def _action(
    handle: str,
    text: str,
    *,
    role: str = "button",
    href: str | None = None,
    hint: str = "other",
) -> PerceivedAction:
    return PerceivedAction(
        handle=handle,
        text=text,
        name=text,
        role=role,
        href=href,
        kind_hint=hint,
    )


def _perception(
    *,
    fields=None,
    actions=None,
    signals=None,
    title="Universal Registration",
    text="",
    signature="sha256:test-page",
) -> Perception:
    return Perception(
        page_signature=signature,
        url="https://regn.example.gov.in/apply",
        title=title,
        visible_text=text,
        fields=fields or [],
        actions=actions or [],
        signals=signals or {},
    )


def test_date_fields_are_understood_by_label_not_placeholder():
    perception = _perception(
        fields=[
            _field("fp-1", "Date of Birth", placeholder="DD-MM-YYYY", required=True),
            _field("fp-2", "Date of Passing", placeholder="DD-MM-YYYY", required=True),
        ],
        text="Personal Details",
    )

    brief = build_deterministic_brief(perception)
    by_handle = {question.handle: question for question in brief.questions}

    assert brief.page_type in {"FORM", "SECTION_FORM"}
    assert by_handle["fp-1"].asked == "Date of Birth"
    assert by_handle["fp-1"].concept == "date_of_birth"
    assert by_handle["fp-1"].expected_format == "DD-MM-YYYY"
    assert by_handle["fp-1"].asked != "DD-MM-YYYY"
    assert by_handle["fp-2"].asked == "Date of Passing"
    assert by_handle["fp-2"].concept is None
    assert any("placeholder" in item.description for item in brief.ambiguities)


def test_name_parts_are_distinct_and_name_as_matric_is_its_own_concept():
    perception = _perception(
        fields=[
            _field("fp-1", "First Name", required=True),
            _field("fp-2", "Middle Name"),
            _field("fp-3", "Last Name", required=True),
            _field("fp-4", "Name as printed on matric certificate", required=True),
        ]
    )

    brief = build_deterministic_brief(perception)
    concepts = [question.concept for question in brief.questions]

    assert concepts == ["first_name", "middle_name", "last_name", "name_as_matric"]
    assert brief.questions[1].required is False
    assert brief.questions[1].concept_label == "Middle name"


def test_a_placeholder_alone_is_never_a_question():
    perception = _perception(
        fields=[_field("fp-1", "", placeholder="DD-MM-YYYY", required=True)],
    )

    brief = build_deterministic_brief(perception)
    question = brief.questions[0]

    assert question.asked == "Untitled question"
    assert question.concept is None
    assert question.expected_format == "DD-MM-YYYY"
    assert any("does not match a known concept" in item.description for item in brief.ambiguities)


def test_landing_page_offers_paths_and_asks_the_human_to_choose():
    perception = _perception(
        fields=[],
        title="HPSC Online",
        actions=[
            _action("fp-1", "New Registration", role="link", href="/register", hint="register"),
            _action("fp-2", "Candidate Login", role="link", href="/login", hint="login"),
        ],
    )

    brief = build_deterministic_brief(perception)

    assert brief.page_type == "LANDING"
    assert {path.label for path in brief.paths} == {"New Registration", "Candidate Login"}
    assert all(path.needs_human_choice for path in brief.paths)
    assert any("choose:" in item for item in brief.needs_human())


def test_dashboard_lists_information_and_distinct_paths():
    perception = _perception(
        fields=[],
        title="Candidate Dashboard",
        text="Registration ID: HPSC-2026-001 Application status: In progress",
        actions=[
            _action("fp-1", "Preview Universal Registration", role="link", href="/preview", hint="navigation"),
            _action("fp-2", "Proceed for Universal Registration", role="link", href="/apply", hint="navigation"),
        ],
        signals={"has_form": False},
    )

    brief = build_deterministic_brief(perception)
    kinds = {path.label: path.kind for path in brief.paths}

    assert brief.page_type == "DASHBOARD"
    assert kinds["Preview Universal Registration"] == "informational"
    assert kinds["Proceed for Universal Registration"] == "application_action"
    assert all(path.needs_human_choice for path in brief.paths)
    assert any(item.label == "Registration / application ID" for item in brief.information)


def test_otp_and_captcha_are_marked_human_only():
    perception = _perception(
        fields=[_field("fp-1", "Enter OTP", input_type="text")],
        signals={"otp": True, "captcha": False, "live_photo": False, "payment": False},
    )

    brief = build_deterministic_brief(perception)

    assert brief.page_type == "OTP"
    assert brief.questions[0].human_only is True
    assert "otp" in brief.human_only
    assert "final_submit" in brief.human_only


class FakeLLM:
    configured = True

    def __init__(self, content: str):
        self.content = content
        self.calls = 0
        self.config = SimpleNamespace(model="fake-model")

    async def complete(self, messages, **kwargs):
        self.calls += 1
        return {"content": self.content}


def test_model_brief_drops_unknown_handles_and_keeps_every_real_field():
    perception = _perception(
        fields=[
            _field("fp-1", "First Name", required=True),
            _field("fp-2", "Date of Birth", placeholder="DD-MM-YYYY", required=True),
        ]
    )
    model_payload = {
        "page_type": "FORM",
        "title": "Personal Details",
        "purpose": "Collect identity details.",
        "confidence": 0.91,
        "sections": [
            {
                "heading": "Personal Details",
                "questions": [
                    {
                        "handle": "fp-1",
                        "asked": "What is your first name?",
                        "concept": "first_name",
                        "concept_confidence": 0.99,
                        "required": True,
                        "evidence": ["label: First Name"],
                    },
                    {
                        "handle": "fp-999",
                        "asked": "Invented field",
                        "concept": "full_name",
                    },
                ],
            }
        ],
        "paths": [],
    }
    interpreter = PageInterpreter(llm_client=FakeLLM(json.dumps(model_payload)))

    brief = asyncio.run(interpreter.interpret(perception))
    handles = [question.handle for question in brief.questions]

    assert handles == ["fp-1", "fp-2"]
    assert brief.source == "model"
    assert brief.questions[0].asked == "What is your first name?"
    assert brief.questions[1].concept == "date_of_birth"


def test_model_failure_falls_back_to_the_deterministic_brief():
    class BrokenLLM:
        configured = True
        config = SimpleNamespace(model="broken")

        async def complete(self, messages, **kwargs):
            return {"content": "this is not json"}

    perception = _perception(fields=[_field("fp-1", "Date of Birth", placeholder="DD-MM-YYYY")])
    interpreter = PageInterpreter(llm_client=BrokenLLM())

    brief = asyncio.run(interpreter.interpret(perception))

    assert brief.source == "deterministic"
    assert brief.questions[0].concept == "date_of_birth"


def test_cache_reuses_a_brief_for_the_same_page_signature():
    fake = FakeLLM(json.dumps({"page_type": "FORM", "sections": []}))
    interpreter = PageInterpreter(llm_client=fake)
    perception = _perception(fields=[_field("fp-1", "First Name")])

    first = asyncio.run(interpreter.interpret(perception))
    second = asyncio.run(interpreter.interpret(perception))

    assert fake.calls == 1
    assert second.source == "cache"
    assert second.page_signature == first.page_signature


def test_cache_invalidates_when_the_signature_changes():
    cache = PageBriefCache()
    perception = _perception(fields=[_field("fp-1", "First Name")])
    brief = build_deterministic_brief(perception)
    cache.put(perception.page_signature, brief)

    assert cache.get(perception.page_signature) is not None
    cache.invalidate()
    assert cache.get(perception.page_signature) is None


def test_classifier_does_not_call_a_form_a_dashboard():
    perception = _perception(
        fields=[_field("fp-1", "First Name"), _field("fp-2", "Last Name")],
        text="Personal Details Save & Next",
    )
    assert classify_page(perception) in {"FORM", "SECTION_FORM"}
