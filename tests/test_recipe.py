"""Local recipes and structural drift detection."""

from __future__ import annotations

import json

from backend.core.recipe import RecipeStore


def field(key, label, *, name=None, field_type="text", required=True, options=None, locators=None):
    return {
        "key": key,
        "semantic_key": key,
        "suggested_key": None,
        "label": label,
        "name": name or key,
        "type": field_type,
        "required": required,
        "options": options or [],
        "locators": locators or [{"strategy": "id", "value": name or key}],
        "confidence": 94,
        "sensitive": False,
    }


def form_map(
    fields,
    *,
    fingerprint="fp-1",
    page_type="application_form",
    portal="example.gov.in",
    step_heading="",
    active_section_id="",
    form_action="",
    gateways=None,
    next_actions=None,
):
    return {
        "portal": portal,
        "url": f"https://{portal}/apply?token=secret",
        "display_url": f"https://{portal}/apply",
        "page_type": page_type,
        "fingerprint": fingerprint,
        "fingerprint_short": fingerprint[:12],
        "fields": fields,
        "step_heading": step_heading,
        "active_section_id": active_section_id,
        "form_action": form_action,
        "gateways": gateways or [],
        "next_actions": next_actions
        or [{"text": "Save & Next", "blocked": False, "kind": "navigation"}],
    }


def test_recipe_round_trip_never_stores_values(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    fields = [
        {**field("full_name", "Full Name"), "value": "SECRET VALUE", "has_value": True},
        field("dob", "Date of Birth", field_type="date"),
    ]
    saved = store.save_from_form_map(form_map(fields), source="inspect")

    assert saved["version"] == 1
    assert saved["status"] == "draft"
    assert saved["safety"]["values_stored"] is False
    assert saved["safety"]["never_auto_submit"] is True
    assert saved["field_count"] == 2

    on_disk = store.path_for("example.gov.in", "application_form").read_text(encoding="utf-8")
    assert "SECRET VALUE" not in on_disk
    assert "has_value" not in on_disk
    assert "Full Name" in on_disk
    assert "locators" in on_disk

    loaded = store.load_by_id(saved["recipe_id"])
    assert loaded["fingerprint"] == "fp-1"
    assert store.list_recipes()[0]["recipe_id"] == saved["recipe_id"]


def test_recipe_match_is_exact_on_fingerprint(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    store.save_from_form_map(form_map([field("full_name", "Full Name")]))

    matched = store.match(form_map([field("full_name", "Full Name")]))
    assert matched["status"] == "match"
    assert matched["confidence"] == 100
    assert matched["version"] == 1
    assert matched["drift"] is None


def test_recipe_versions_increment_and_report_label_drift(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    store.save_from_form_map(form_map([field("full_name", "Full Name")]))

    drifted = store.match(form_map([field("full_name", "Candidate Name")], fingerprint="fp-2"))
    assert drifted["status"] == "drift"
    assert drifted["confidence"] == 55
    assert drifted["drift"]["changed"][0]["key"] == "full_name"
    assert "label" in drifted["drift"]["changed"][0]["changes"]
    assert drifted["drift"]["requires_repair"] is False

    saved = store.save_from_form_map(form_map([field("full_name", "Candidate Name")], fingerprint="fp-2"))
    assert saved["version"] == 2
    assert saved["previous_fingerprint"] == "fp-1"


def test_removed_or_renamed_fields_require_repair(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    store.save_from_form_map(
        form_map(
            [
                field("full_name", "Full Name", name="full_name"),
                field("dob", "Date of Birth", name="dob", field_type="date"),
            ]
        )
    )

    # Keep the same label but change the semantic key: this is a rename, not a
    # brand-new field, and the recipe must flag it for review.
    renamed_map = form_map(
        [
            field("candidate_name", "Full Name", name="full_name"),
        ],
        fingerprint="fp-renamed",
    )
    drift = store.match(renamed_map)["drift"]

    assert drift["requires_repair"] is True
    assert drift["renamed"][0]["from"] == "full_name"
    assert drift["renamed"][0]["to"] == "candidate_name"
    assert drift["removed"][0]["key"] == "dob"


def test_page_type_change_with_the_same_structure_is_structural_drift(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    store.save_from_form_map(form_map([field("full_name", "Full Name")]))

    # Same fields, different classification: the page still resembles the
    # saved structure, so this is a meaningful change to report.
    login = form_map(
        [field("full_name", "Full Name")],
        fingerprint="fp-login",
        page_type="login",
    )
    result = store.match(login)

    assert result["status"] == "drift"
    assert result["drift"]["page_type_changed"] is True
    assert "login" in result["drift"]["summary"]


def test_multi_step_form_keeps_one_recipe_per_step(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    first = store.save_from_form_map(
        form_map(
            [
                field("full_name", "Full Name", name="fullName"),
                field("dob", "Date of Birth", name="dob"),
            ],
            fingerprint="fp-step-1",
            step_heading="Stage 1: Personal details",
            active_section_id="sec-1",
        )
    )
    second = store.save_from_form_map(
        form_map(
            [
                field("matric_roll", "Matric Roll Number", name="matricRoll"),
                field("matric_board", "Matric Board", name="matricBoard"),
            ],
            fingerprint="fp-step-2",
            step_heading="Stage 2: Academic details",
            active_section_id="sec-2",
        )
    )

    assert first["recipe_id"] != second["recipe_id"]
    assert first["page_key"] != second["page_key"]
    assert "sec_sec_1" in first["page_key"]
    assert "sec_sec_2" in second["page_key"]
    assert len(store.list_recipes()) == 2

    step_one = store.match(
        form_map(
            [
                field("full_name", "Full Name", name="fullName"),
                field("dob", "Date of Birth", name="dob"),
            ],
            fingerprint="fp-step-1",
            step_heading="Stage 1: Personal details",
            active_section_id="sec-1",
        )
    )
    step_two = store.match(
        form_map(
            [
                field("matric_roll", "Matric Roll Number", name="matricRoll"),
                field("matric_board", "Matric Board", name="matricBoard"),
            ],
            fingerprint="fp-step-2",
            step_heading="Stage 2: Academic details",
            active_section_id="sec-2",
        )
    )

    assert step_one["status"] == "match"
    assert step_one["recipe_id"] == first["recipe_id"]
    assert step_two["status"] == "match"
    assert step_two["recipe_id"] == second["recipe_id"]


def test_different_step_is_new_not_drift(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    store.save_from_form_map(
        form_map(
            [field("full_name", "Full Name")],
            fingerprint="fp-step-1",
            step_heading="Stage 1: Personal details",
            active_section_id="sec-1",
        )
    )

    next_step = store.match(
        form_map(
            [field("matric_roll", "Matric Roll Number")],
            fingerprint="fp-step-2",
            step_heading="Stage 2: Academic details",
            active_section_id="sec-2",
        )
    )

    assert next_step["status"] == "new"
    assert next_step["drift"] is None


def test_landing_page_is_new_not_drift(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    store.save_from_form_map(
        form_map(
            [field("full_name", "Full Name")],
            fingerprint="fp-apply",
            step_heading="Application form",
            active_section_id="sec-1",
        )
    )

    landing = store.match(
        form_map([], fingerprint="fp-landing", page_type="portal_entry")
    )

    assert landing["status"] == "new"
    assert landing["drift"] is None


def test_heading_rename_versions_the_same_step(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    fields = [field("full_name", "Full Name"), field("dob", "Date of Birth")]
    first = store.save_from_form_map(
        form_map(
            fields,
            fingerprint="fp-1",
            step_heading="Stage 1: Personal details",
            active_section_id="sec-1",
        )
    )

    renamed = store.save_from_form_map(
        form_map(
            fields,
            fingerprint="fp-2",
            step_heading="Step 1: Candidate details",
            active_section_id="sec-1",
        )
    )

    assert len(store.list_recipes()) == 1
    assert renamed["recipe_id"] == first["recipe_id"]
    assert renamed["version"] == 2
    assert renamed["page_key"] != first["page_key"]
    assert renamed["previous_page_key"] == first["page_key"]

    matched = store.match(
        form_map(
            fields,
            fingerprint="fp-2",
            step_heading="Step 1: Candidate details",
            active_section_id="sec-1",
        )
    )
    assert matched["status"] == "match"
    assert matched["recipe_id"] == first["recipe_id"]


def test_similar_step_drift_is_reported_against_the_right_recipe(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    store.save_from_form_map(
        form_map(
            [field("full_name", "Full Name")],
            fingerprint="fp-step-1",
            step_heading="Stage 1: Personal details",
            active_section_id="sec-1",
        )
    )
    second = store.save_from_form_map(
        form_map(
            [
                field("matric_roll", "Matric Roll Number"),
                field("matric_board", "Matric Board"),
            ],
            fingerprint="fp-step-2",
            step_heading="Stage 2: Academic details",
            active_section_id="sec-2",
        )
    )

    # One extra field on step 2 is a drift of that step, not of step 1.
    drifted = store.match(
        form_map(
            [
                field("matric_roll", "Matric Roll Number"),
                field("matric_board", "Matric Board"),
                field("matric_year", "Year of Passing"),
            ],
            fingerprint="fp-step-2b",
            step_heading="Stage 2: Academic details",
            active_section_id="sec-2",
        )
    )

    assert drifted["status"] == "drift"
    assert drifted["recipe_id"] == second["recipe_id"]
    assert drifted["drift"]["added"][0]["key"] == "matric_year"


def test_form_action_path_separates_reused_step_markup(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    fields = [field("full_name", "Full Name")]

    first = store.save_from_form_map(
        form_map(
            fields,
            fingerprint="fp-action-1",
            step_heading="Application",
            form_action="/apply/personal",
        )
    )
    second = store.save_from_form_map(
        form_map(
            fields,
            fingerprint="fp-action-2",
            step_heading="Application",
            form_action="/apply/address?session=secret",
        )
    )

    assert first["recipe_id"] != second["recipe_id"]
    assert "personal" in first["page_key"]
    assert "address" in second["page_key"]
    assert len(store.list_recipes()) == 2


def test_long_recipe_id_round_trips_through_load_by_id(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    saved = store.save_from_form_map(
        form_map(
            [field("full_name", "Full Name")],
            portal="a" * 110 + ".gov.in",
            step_heading="Candidate personal details " * 4,
            active_section_id="section-" + "x" * 80,
        )
    )

    assert len(saved["recipe_id"]) > 120
    loaded = store.load_by_id(saved["recipe_id"])
    assert loaded is not None
    assert loaded["recipe_id"] == saved["recipe_id"]


def test_recipe_summary_omits_field_content(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    saved = store.save_from_form_map(form_map([field("full_name", "Full Name")]))
    summary = RecipeStore.summary(saved)

    assert "fields" not in summary
    assert summary["field_count"] == 1
    assert summary["fingerprint_short"] == "fp-1"
    assert summary["page_key"] == ""
    assert json.dumps(summary)


def test_recipe_keeps_durable_gateway_locators_but_not_scan_ids(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    saved = store.save_from_form_map(
        form_map(
            [field("full_name", "Full Name")],
            gateways=[
                {
                    "type": "LOGIN",
                    "text": "Login",
                    "id": None,
                    "name": None,
                    "tag": "a",
                    "role": "link",
                    "href": "/frontend/site/login",
                    "element_id": "fp-scan-123-11",
                    "frame": "main",
                    "css": 'a[href="/frontend/site/login"]',
                    "css_unique": True,
                    "xpath": "/html/body/nav[1]/div/a[2]",
                    "element_hash": "0d889999",
                    "covered_by": {"tag": "div"},
                }
            ],
            next_actions=[
                {
                    "text": "Save & Next",
                    "element_id": "fp-scan-123-42",
                    "css": "#save-next",
                    "kind": "navigation",
                    "blocked": False,
                }
            ],
        )
    )

    serialized = json.dumps(saved)
    assert "fp-scan-123" not in serialized
    assert "covered_by" not in serialized

    gateway = saved["gateways"][0]
    assert gateway["role"] == "link"
    assert gateway["href"] == "/frontend/site/login"
    assert gateway["css"] == 'a[href="/frontend/site/login"]'
    assert gateway["xpath"] == "/html/body/nav[1]/div/a[2]"
    assert gateway["element_hash"] == "0d889999"

    action = saved["next_actions"][0]
    assert action["css"] == "#save-next"
    assert "element_id" not in action


def test_atomic_write_leaves_no_temporary_files(tmp_path):
    store = RecipeStore(tmp_path / "recipes")
    store.save_from_form_map(form_map([field("full_name", "Full Name")]))

    assert list(store.root.glob("*.tmp")) == []
