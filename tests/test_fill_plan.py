"""Fill-plan tests: meaning decides what may be typed, and how."""

from __future__ import annotations

from backend.core.facts import FactBook
from backend.core.fill_plan import build_fill_plan, format_date_value, parse_date
from backend.core.perception import Perception, PerceivedField
from backend.core.vault import CandidateVault


class _Manager:
    def __init__(self, profile):
        self.vault = profile


def _book(tmp_path, profile: CandidateVault) -> FactBook:
    return FactBook(str(tmp_path / "facts.json"), vault_manager=_Manager(profile))


def _perception(*fields: PerceivedField) -> Perception:
    return Perception(
        page_signature="sha256:fill-plan",
        url="https://regn.example.gov.in/apply",
        title="Personal Details",
        fields=list(fields),
    )


def _field(handle: str, label: str, **kwargs) -> PerceivedField:
    return PerceivedField(handle=handle, label_text=label, **kwargs)


def test_name_parts_are_filled_from_derived_parts(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Aman Kumar Sharma"))
    perception = _perception(
        _field("fp-1", "First Name"),
        _field("fp-2", "Middle Name"),
        _field("fp-3", "Last Name"),
    )

    plan = build_fill_plan(perception, book, domain="regn.example.gov.in")

    assert [plan[handle].state for handle in ("fp-1", "fp-2", "fp-3")] == ["fill", "fill", "fill"]
    assert [plan[handle].value for handle in ("fp-1", "fp-2", "fp-3")] == ["Aman", "Kumar", "Sharma"]


def test_a_known_absent_middle_name_is_left_blank_not_asked(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Nishant Kumar"))
    book.set_fact(
        "full_name",
        value="Nishant Kumar",
        parts={
            "first": "Nishant",
            "middle": None,
            "middle_known_absent": True,
            "last": "Kumar",
        },
    )
    perception = _perception(_field("fp-1", "Middle Name"))

    plan = build_fill_plan(perception, book)

    assert plan["fp-1"].state == "leave_blank"
    assert plan["fp-1"].value == ""
    assert "no middle name" in plan["fp-1"].reason


def test_two_token_name_leaves_middle_name_blank(tmp_path):
    """The exact live HPSC case: "Nishant Kumar" must not ask for a middle name."""
    book = _book(tmp_path, CandidateVault(full_name="Nishant Kumar"))
    perception = _perception(_field("fp-1", "Middle Name"))

    plan = build_fill_plan(perception, book)

    assert plan["fp-1"].state == "leave_blank"
    assert plan["fp-1"].value == ""


def test_name_as_matric_is_proposed_but_not_filled_without_confirmation(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name="Aman Kumar Sharma"))
    perception = _perception(_field("fp-1", "Name as printed on matric certificate"))

    plan = build_fill_plan(perception, book)

    assert plan["fp-1"].state == "confirm"
    assert plan["fp-1"].value == "Aman Kumar Sharma"


def test_a_date_is_rendered_in_the_format_the_page_asked_for(tmp_path):
    book = _book(tmp_path, CandidateVault(dob="2003-08-15"))
    perception = _perception(
        _field("fp-1", "Date of Birth", placeholder="DD/MM/YYYY"),
    )

    plan = build_fill_plan(perception, book)

    assert plan["fp-1"].state == "fill"
    assert plan["fp-1"].value == "15/08/2003"


def test_otp_is_never_filled(tmp_path):
    book = _book(tmp_path, CandidateVault())
    perception = _perception(_field("fp-1", "Enter OTP"))

    plan = build_fill_plan(perception, book)

    assert plan["fp-1"].state == "human_only"


def test_an_unknown_question_falls_back_instead_of_guessing(tmp_path):
    book = _book(tmp_path, CandidateVault())
    perception = _perception(_field("fp-1", "Favourite colour of your first teacher"))

    plan = build_fill_plan(perception, book)

    assert plan["fp-1"].state == "fallback"
    assert plan["fp-1"].concept is None


def test_a_missing_fact_is_asked_not_invented(tmp_path):
    book = _book(tmp_path, CandidateVault(full_name=""))
    perception = _perception(_field("fp-1", "First Name"))

    plan = build_fill_plan(perception, book)

    assert plan["fp-1"].state == "ask_human"
    assert plan["fp-1"].value is None


def test_a_select_must_offer_the_value(tmp_path):
    book = _book(tmp_path, CandidateVault(gender="Male"))
    matching = _perception(
        _field(
            "fp-1",
            "Gender",
            tag="select",
            input_type="select",
            options=[{"text": "Female", "value": "F"}, {"text": "Male", "value": "M"}],
        )
    )
    mismatched = _perception(
        _field(
            "fp-2",
            "Gender",
            tag="select",
            input_type="select",
            options=[{"text": "Female", "value": "F"}],
        )
    )

    assert build_fill_plan(matching, book)["fp-1"].value == "M"
    assert build_fill_plan(mismatched, book)["fp-2"].state == "ask_human"


def test_a_file_question_is_an_upload_not_a_text_fact(tmp_path):
    book = _book(tmp_path, CandidateVault())
    perception = _perception(_field("fp-1", "Passport Photograph", input_type="file"))

    plan = build_fill_plan(perception, book)

    assert plan["fp-1"].state == "upload"


def test_date_helpers_cover_common_shapes():
    assert parse_date("2003-08-15") == (2003, 8, 15)
    assert parse_date("15/08/2003") == (2003, 8, 15)
    assert parse_date("not a date") is None
    assert format_date_value("2003-08-15", "DD-MM-YYYY") == "15-08-2003"
    assert format_date_value("15/08/2003", "YYYY/MM/DD") == "2003/08/15"
    assert format_date_value("2003-08-15", None) == "2003-08-15"
