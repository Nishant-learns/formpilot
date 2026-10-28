"""Canonical human concepts used by the interpreter.

A concept is the meaning of a question, independent of the portal's label,
framework name or placeholder.  ``date_of_birth`` is the same concept whether
the page says "Date of Birth", "DOB", "When were you born?" or "जन्म तिथि".

The field registry remains the fast path for values.  This module is the
dictionary the interpreter uses to turn a human question into a concept before
it asks the vault for an answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Concept:
    key: str
    label: str
    answer_type: str = "text"
    vault_key: Optional[str] = None
    aliases: tuple[str, ...] = field(default_factory=tuple)


def _c(
    key: str,
    label: str,
    answer_type: str = "text",
    vault_key: Optional[str] = None,
    aliases: tuple[str, ...] = (),
) -> Concept:
    return Concept(
        key=key,
        label=label,
        answer_type=answer_type,
        vault_key=vault_key,
        aliases=aliases,
    )


CONCEPTS: Dict[str, Concept] = {
    # Identity
    "full_name": _c(
        "full_name",
        "Full name",
        vault_key="full_name",
        aliases=("full name", "candidate name", "applicant name", "student name"),
    ),
    "first_name": _c(
        "first_name",
        "First name",
        aliases=("first name", "given name", "forename"),
    ),
    "middle_name": _c(
        "middle_name",
        "Middle name",
        aliases=("middle name",),
    ),
    "last_name": _c(
        "last_name",
        "Last name",
        aliases=("last name", "surname", "family name"),
    ),
    "name_as_matric": _c(
        "name_as_matric",
        "Name as per matric certificate",
        aliases=(
            "name as per matric",
            "name as printed on matric certificate",
            "name as per 10th certificate",
        ),
    ),
    "father_name": _c("father_name", "Father's name", vault_key="father_name"),
    "mother_name": _c("mother_name", "Mother's name", vault_key="mother_name"),
    "date_of_birth": _c(
        "date_of_birth",
        "Date of birth",
        answer_type="date",
        vault_key="dob",
        aliases=("date of birth", "dob", "birth date", "birthday"),
    ),
    "gender": _c("gender", "Gender", "select", "gender"),
    "marital_status": _c("marital_status", "Marital status", "select", "marital_status"),
    "religion": _c("religion", "Religion", "select", "religion"),
    "nationality": _c("nationality", "Nationality", "text", "nationality"),
    "category": _c("category", "Social category", "select", "category"),
    "sub_caste": _c("sub_caste", "Sub caste", "text", "sub_caste"),
    "domicile_state": _c("domicile_state", "Domicile state", "select", "domicile_state"),
    "is_differently_abled": _c(
        "is_differently_abled", "Differently abled", "select", "is_differently_abled"
    ),
    "is_ex_serviceman": _c(
        "is_ex_serviceman", "Ex-serviceman", "select", "is_ex_serviceman"
    ),
    "disability_type": _c("disability_type", "Disability type", "text", "disability_type"),
    "disability_percentage": _c(
        "disability_percentage", "Disability percentage", "text", "disability_percentage"
    ),
    "caste_certificate_number": _c(
        "caste_certificate_number", "Caste certificate number", vault_key="caste_certificate_number"
    ),
    "caste_cert_issue_date": _c(
        "caste_cert_issue_date", "Caste certificate issue date", "date", "caste_cert_issue_date"
    ),
    "caste_cert_authority": _c(
        "caste_cert_authority", "Caste certificate authority", vault_key="caste_cert_authority"
    ),
    "domicile_certificate_number": _c(
        "domicile_certificate_number",
        "Domicile certificate number",
        vault_key="domicile_certificate_number",
    ),
    "has_aadhaar": _c("has_aadhaar", "Has Aadhaar", "select", "has_aadhaar"),
    "same_as_permanent": _c(
        "same_as_permanent", "Present address same as permanent", "select", "same_as_permanent"
    ),
    # Confirmation fields repeat an existing fact.  They keep their own concept
    # so the page brief can say "confirmation", but the fact resolves to the
    # parent concept rather than being stored twice.
    "verify_full_name": _c(
        "verify_full_name", "Confirm full name", vault_key="verify_full_name"
    ),
    "verify_father_name": _c(
        "verify_father_name", "Confirm father's name", vault_key="verify_father_name"
    ),
    "verify_mother_name": _c(
        "verify_mother_name", "Confirm mother's name", vault_key="verify_mother_name"
    ),
    # Identifiers and credentials
    "registration_id": _c(
        "registration_id", "Registration / OTR ID", vault_key="registration_id"
    ),
    "account_password": _c(
        "account_password", "Account password", "password", "account_password"
    ),
    "aadhaar_number": _c("aadhaar_number", "Aadhaar number", "text", "aadhaar_number"),
    "apaar_id": _c("apaar_id", "APAAR ID", "text", "custom_fields.apaar_id"),
    "digilocker_id": _c(
        "digilocker_id", "DigiLocker ID", "text", "custom_fields.digilocker_id"
    ),
    "identification_mark_1": _c(
        "identification_mark_1", "Identification mark 1", "text", "identification_mark_1"
    ),
    "identification_mark_2": _c(
        "identification_mark_2", "Identification mark 2", "text", "identification_mark_2"
    ),
    # Contact
    "mobile": _c("mobile", "Mobile number", "tel", "mobile"),
    "alternate_mobile": _c("alternate_mobile", "Alternate mobile", "tel", "alternate_mobile"),
    "email": _c("email", "Email address", "email", "email"),
    "confirm_email": _c("confirm_email", "Confirm email address", "email", "confirm_email"),
    # Address
    "address_line_1": _c("address_line_1", "Address line 1", vault_key="address_line_1"),
    "address_line_2": _c("address_line_2", "Address line 2", vault_key="address_line_2"),
    "village_town_city": _c(
        "village_town_city", "Village / town / city", vault_key="village_town_city"
    ),
    "district": _c("district", "District", vault_key="district"),
    "state": _c("state", "State", vault_key="state"),
    "pincode": _c("pincode", "PIN code", "tel", "pincode"),
    "present_address_line_1": _c(
        "present_address_line_1", "Present address", vault_key="present_address_line_1"
    ),
    "present_district": _c("present_district", "Present district", vault_key="present_district"),
    "present_state": _c("present_state", "Present state", vault_key="present_state"),
    "present_pincode": _c("present_pincode", "Present PIN code", "tel", "present_pincode"),
    # Matric / 10th
    "matric_board": _c("matric_board", "10th / matric board", "select", "matric.board"),
    "matric_roll_number": _c(
        "matric_roll_number", "10th / matric roll number", vault_key="matric.roll_number"
    ),
    "matric_roll_code": _c("matric_roll_code", "10th / matric roll code", vault_key="matric.roll_code"),
    "matric_passing_year": _c(
        "matric_passing_year", "Matric passing year", vault_key="matric.passing_year"
    ),
    "matric_total_marks": _c(
        "matric_total_marks", "Matric total marks", vault_key="matric.total_marks"
    ),
    "matric_obtained_marks": _c(
        "matric_obtained_marks", "Matric obtained marks", vault_key="matric.obtained_marks"
    ),
    "matric_percentage": _c(
        "matric_percentage", "Matric percentage", vault_key="matric.percentage"
    ),
    "matric_cgpa": _c("matric_cgpa", "Matric CGPA", vault_key="matric.cgpa"),
    "matric_school_name": _c(
        "matric_school_name", "Matric school name", vault_key="matric.school_name"
    ),
    "matric_certificate_number": _c(
        "matric_certificate_number", "Matric certificate number", vault_key="matric.certificate_number"
    ),
    # Intermediate / 12th
    "intermediate_board": _c(
        "intermediate_board", "12th / intermediate board", "select", "intermediate.board"
    ),
    "intermediate_stream": _c(
        "intermediate_stream", "Intermediate stream", "select", "intermediate.stream"
    ),
    "intermediate_roll_number": _c(
        "intermediate_roll_number", "Intermediate roll number", vault_key="intermediate.roll_number"
    ),
    "intermediate_roll_code": _c(
        "intermediate_roll_code", "Intermediate roll code", vault_key="intermediate.roll_code"
    ),
    "intermediate_passing_year": _c(
        "intermediate_passing_year", "Intermediate passing year", vault_key="intermediate.passing_year"
    ),
    "intermediate_total_marks": _c(
        "intermediate_total_marks", "Intermediate total marks", vault_key="intermediate.total_marks"
    ),
    "intermediate_obtained_marks": _c(
        "intermediate_obtained_marks", "Intermediate obtained marks", vault_key="intermediate.obtained_marks"
    ),
    "intermediate_percentage": _c(
        "intermediate_percentage", "Intermediate percentage", vault_key="intermediate.percentage"
    ),
    "intermediate_college_name": _c(
        "intermediate_college_name", "Intermediate college name", vault_key="intermediate.college_name"
    ),
    "intermediate_certificate_number": _c(
        "intermediate_certificate_number",
        "Intermediate certificate number",
        vault_key="intermediate.certificate_number",
    ),
    # Graduation
    "graduation_degree_name": _c(
        "graduation_degree_name", "Graduation degree", vault_key="graduation.degree_name"
    ),
    "graduation_university": _c(
        "graduation_university", "Graduation university", vault_key="graduation.university"
    ),
    "graduation_passing_year": _c(
        "graduation_passing_year", "Graduation passing year", vault_key="graduation.passing_year"
    ),
    "graduation_roll_number": _c(
        "graduation_roll_number", "Graduation roll number", vault_key="graduation.roll_number"
    ),
    "graduation_cgpa": _c("graduation_cgpa", "Graduation CGPA", vault_key="graduation.cgpa"),
    "graduation_percentage": _c(
        "graduation_percentage", "Graduation percentage", vault_key="graduation.percentage"
    ),
    # Uploads
    "photo_upload": _c("photo_upload", "Passport photograph", "file", "photo_path"),
    "signature_upload": _c("signature_upload", "Digital signature", "file", "signature_path"),
    "matric_cert_upload": _c(
        "matric_cert_upload", "Matric certificate", "file", "matric_cert_path"
    ),
    # Other common questions
    "height_cm": _c("height_cm", "Height (cm)", "text", "custom_fields.height_cm"),
    "chest_cm": _c("chest_cm", "Chest (cm)", "text", "custom_fields.chest_cm"),
    "mother_tongue": _c(
        "mother_tongue", "Mother tongue", "text", "custom_fields.mother_tongue"
    ),
    "employment_status": _c(
        "employment_status", "Employment status", "select", "custom_fields.employment_status"
    ),
    "criminal_case_pending": _c(
        "criminal_case_pending",
        "Criminal case pending",
        "select",
        "custom_fields.criminal_case_pending",
    ),
    "debarred_from_exam": _c(
        "debarred_from_exam",
        "Debarred from exam",
        "select",
        "custom_fields.debarred_from_exam",
    ),
}


@dataclass
class ConceptMatch:
    concept: Optional[str] = None
    confidence: float = 0.0
    answer_type: str = "text"
    expected_format: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    human_only: bool = False
    verify: bool = False
    reason: str = ""


_DATE_TOKENS = re.compile(r"\b(DD|MM|YYYY|YY)\b", re.IGNORECASE)
_DATE_SEQUENCE = re.compile(
    r"\b(DD|MM|YYYY|YY)\s*([/\-. ])\s*(DD|MM|YYYY|YY)\s*\2\s*(DD|MM|YYYY|YY)\b",
    re.IGNORECASE,
)
_VERIFY_RE = re.compile(r"\b(confirm|verify|re[-\s]?enter|repeat|retype)\b", re.IGNORECASE)
_HUMAN_ONLY_RE = re.compile(
    r"\botp\b|one[-\s]?time\s*(password|code)|verification\s*code|"
    r"auth(?:entication)?\s*code|captcha|security\s*check|code\s*(?:shown|above)",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    value = (text or "").lower().replace("&", " and ").replace("'", "")
    value = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def concept_label(key: Optional[str]) -> str:
    if not key:
        return ""
    concept = CONCEPTS.get(key)
    return concept.label if concept else key.replace("_", " ")


def expected_date_format(text: str) -> Optional[str]:
    """Return an explicit date format such as ``DD-MM-YYYY`` if one is shown."""
    match = _DATE_SEQUENCE.search(text or "")
    if match:
        return f"{match.group(1).upper()}{match.group(2)}{match.group(3).upper()}{match.group(2)}{match.group(4).upper()}"
    tokens = [token.upper() for token in _DATE_TOKENS.findall(text or "")]
    if len(tokens) == 3 and {"DD", "MM"} <= set(tokens):
        return "-".join(tokens)
    return None


def answer_type_for(input_type: str, tag: str = "input") -> str:
    value = (input_type or "").lower()
    if tag == "select":
        return "select"
    if tag == "textarea":
        return "textarea"
    if value in {"email", "tel", "url", "number", "date", "datetime-local", "time", "month", "week"}:
        return value
    if value in {"checkbox", "radio", "file"}:
        return value
    if value == "password":
        return "password"
    return "text"


def _rule(label: str, pattern: str) -> bool:
    return re.search(pattern, label, re.IGNORECASE) is not None


def match_question(
    label_text: str,
    *,
    placeholder: str = "",
    helper_text: str = "",
    group_heading: str = "",
    input_type: str = "text",
    tag: str = "input",
) -> ConceptMatch:
    """Turn a human question into a canonical concept.

    The label and helper text carry meaning.  The placeholder is only ever a
    format hint; it is never the identity of the field.
    """
    label = normalize(label_text)
    helper = normalize(helper_text)
    source = label or helper
    evidence: List[str] = []
    if label_text.strip():
        evidence.append(f"label: {label_text.strip()}")
    if helper_text.strip() and helper_text.strip() != label_text.strip():
        evidence.append(f"helper: {helper_text.strip()}")
    if group_heading.strip():
        evidence.append(f"group: {group_heading.strip()}")

    expected_format = expected_date_format(" ".join([label_text, helper_text, placeholder]))
    if (input_type or "").lower() == "date":
        expected_format = "YYYY-MM-DD"

    if not source:
        if placeholder.strip():
            evidence.append(f"placeholder: {placeholder.strip()} (format hint only)")
        return ConceptMatch(
            answer_type=answer_type_for(input_type, tag),
            expected_format=expected_format,
            evidence=evidence,
            reason="The field has no human label, so its meaning is unknown.",
        )

    if _HUMAN_ONLY_RE.search(source):
        return ConceptMatch(
            human_only=True,
            answer_type=answer_type_for(input_type, tag),
            expected_format=expected_format,
            evidence=evidence,
            reason="One-time codes and security challenges are human-only.",
        )

    verify = bool(_VERIFY_RE.search(source))
    context = normalize(" ".join([label_text, group_heading]))

    def hit(key: str, confidence: float, reason: str) -> ConceptMatch:
        concept = CONCEPTS.get(key)
        return ConceptMatch(
            concept=key,
            confidence=confidence,
            answer_type=concept.answer_type if concept else answer_type_for(input_type, tag),
            expected_format=expected_format,
            evidence=evidence,
            verify=verify,
            reason=reason,
        )

    # Human-only and security fields are matched before anything else.
    if _rule(source, r"mother\s*tongue|native\s*language"):
        return hit("mother_tongue", 0.92, "The question asks for the mother tongue.")

    # A file field is a document request, not a text fact.  This check runs
    # before the academic-number rules so "Matric Certificate" upload is not
    # mistaken for a certificate number.
    if (input_type or "").lower() == "file":
        if _rule(source, r"photo|photograph|passport\s*size|passport\s*photo"):
            return hit("photo_upload", 0.95, "The question asks for a photograph upload.")
        if _rule(source, r"signature|sign"):
            return hit("signature_upload", 0.94, "The question asks for a signature upload.")
        if _rule(source, r"matric.*(certificate|marksheet)|10th.*(certificate|marksheet)"):
            return hit("matric_cert_upload", 0.93, "The question asks for a matric certificate upload.")
        if _rule(source, r"certificate|marksheet|document|proof"):
            return ConceptMatch(
                answer_type="file",
                expected_format=expected_format,
                evidence=evidence,
                verify=verify,
                reason="The page asks for a document upload but the exact document is unclear.",
            )

    if _rule(source, r"father|guardian"):
        return hit("father_name", 0.95, "The question asks for the father's or guardian's name.")

    if _rule(source, r"mother"):
        return hit("mother_name", 0.95, "The question asks for the mother's name.")

    # "Name as per matric certificate" is a specific identity fact, not a
    # generic full name.
    if _rule(source, r"name") and _rule(context, r"matric|10th|high\s*school|matriculation"):
        return hit(
            "name_as_matric",
            0.92,
            "The question asks for the name exactly as it appears on the matric certificate.",
        )

    if _rule(source, r"first\s*name|given\s*name|forename"):
        return hit("first_name", 0.95, "The question asks for the first name.")
    if _rule(source, r"middle\s*name"):
        return hit("middle_name", 0.95, "The question asks for the middle name.")
    if _rule(source, r"last\s*name|surname|family\s*name"):
        return hit("last_name", 0.95, "The question asks for the last name.")
    if _rule(source, r"full\s*name|candidate\s*name|applicant\s*name|student\s*name|your\s*name"):
        return hit("full_name", 0.93, "The question asks for the full name.")

    if _rule(source, r"\bdob\b|date\s*of\s*birth|birth\s*date|birthday|when\s*were\s*you\s*born|जन्म"):
        return hit("date_of_birth", 0.96, "The question asks for the date of birth.")

    if _rule(source, r"\bgender\b|\bsex\b"):
        return hit("gender", 0.95, "The question asks for gender.")
    if _rule(source, r"marital"):
        return hit("marital_status", 0.94, "The question asks for marital status.")
    if _rule(source, r"religion"):
        return hit("religion", 0.94, "The question asks for religion.")
    if _rule(source, r"nationality"):
        return hit("nationality", 0.94, "The question asks for nationality.")

    if _rule(source, r"sub\s*caste|subcaste"):
        return hit("sub_caste", 0.94, "The question asks for the sub-caste.")
    if _rule(source, r"category|caste|community|social\s*status"):
        return hit("category", 0.9, "The question asks for the social category.")
    if _rule(source, r"domicile|state\s*of\s*origin"):
        return hit("domicile_state", 0.92, "The question asks for the domicile state.")
    if _rule(source, r"differently\s*abled|disab|pwd"):
        return hit("is_differently_abled", 0.9, "The question asks about disability.")
    if _rule(source, r"ex[-\s]*serviceman"):
        return hit("is_ex_serviceman", 0.94, "The question asks about ex-serviceman status.")

    if _rule(source, r"alternate\s*(mobile|phone)|secondary\s*(mobile|phone)"):
        return hit("alternate_mobile", 0.93, "The question asks for an alternate mobile number.")
    if _rule(source, r"mobile|phone|contact\s*(no|number)|cell|whatsapp"):
        return hit("mobile", 0.94, "The question asks for a mobile number.")
    if _rule(source, r"confirm\s*email|verify\s*email|re[-\s]?enter\s*email"):
        return hit("confirm_email", 0.94, "The question asks to confirm the email address.")
    if _rule(source, r"email|mail\s*id|e[-\s]*mail"):
        return hit("email", 0.94, "The question asks for an email address.")

    if _rule(source, r"aadhaar|aadhar|uidai"):
        return hit("aadhaar_number", 0.95, "The question asks for the Aadhaar number.")
    if _rule(source, r"apaar"):
        return hit("apaar_id", 0.94, "The question asks for the APAAR ID.")
    if _rule(source, r"digilocker"):
        return hit("digilocker_id", 0.94, "The question asks for the DigiLocker ID.")
    if _rule(source, r"identification\s*mark\s*2|id\s*mark\s*2"):
        return hit("identification_mark_2", 0.9, "The question asks for the second identification mark.")
    if _rule(source, r"identification\s*mark|id\s*mark"):
        return hit("identification_mark_1", 0.9, "The question asks for an identification mark.")
    if _rule(source, r"height"):
        return hit("height_cm", 0.9, "The question asks for height.")
    if _rule(source, r"chest"):
        return hit("chest_cm", 0.9, "The question asks for chest measurement.")
    if _rule(source, r"employment|occupation"):
        return hit("employment_status", 0.88, "The question asks for employment status.")
    if _rule(source, r"criminal"):
        return hit("criminal_case_pending", 0.9, "The question asks about a pending criminal case.")
    if _rule(source, r"debarred"):
        return hit("debarred_from_exam", 0.92, "The question asks about being debarred.")

    if _rule(source, r"registration\s*(id|no|number)|reg\s*(id|no|number)|\botr\b|application\s*(id|no|number)"):
        return hit("registration_id", 0.92, "The question asks for a registration identifier.")
    if _rule(source, r"password|passcode"):
        return hit("account_password", 0.93, "The question asks for a password.")

    if _rule(source, r"present\s*pin|correspondence\s*pin"):
        return hit("present_pincode", 0.92, "The question asks for the present PIN code.")
    if _rule(source, r"pin\s*code|pincode|postal\s*code|\bzip\b"):
        return hit("pincode", 0.94, "The question asks for a PIN code.")
    if _rule(source, r"present\s*district|correspondence\s*district"):
        return hit("present_district", 0.92, "The question asks for the present district.")
    if _rule(source, r"present\s*state|correspondence\s*state"):
        return hit("present_state", 0.92, "The question asks for the present state.")
    if _rule(source, r"present\s*address|correspondence\s*address"):
        return hit("present_address_line_1", 0.9, "The question asks for the present address.")
    if _rule(source, r"district"):
        return hit("district", 0.92, "The question asks for the district.")
    if _rule(source, r"\bstate\b"):
        return hit("state", 0.9, "The question asks for the state.")
    if _rule(source, r"village|town|city"):
        return hit("village_town_city", 0.9, "The question asks for the village, town or city.")
    if _rule(source, r"address\s*line\s*2|address\s*2"):
        return hit("address_line_2", 0.9, "The question asks for the second address line.")
    if _rule(source, r"address"):
        return hit("address_line_1", 0.88, "The question asks for an address.")

    # Academic records.  The qualification prefix decides the section.
    if _rule(context, r"matric|10th|high\s*school|matriculation"):
        if _rule(source, r"board"):
            return hit("matric_board", 0.94, "The question asks for the matric board.")
        if _rule(source, r"roll\s*code"):
            return hit("matric_roll_code", 0.92, "The question asks for the matric roll code.")
        if _rule(source, r"roll"):
            return hit("matric_roll_number", 0.93, "The question asks for the matric roll number.")
        if _rule(source, r"passing\s*year|year\s*of\s*passing|passing"):
            return hit("matric_passing_year", 0.92, "The question asks for the matric passing year.")
        if _rule(source, r"total\s*marks"):
            return hit("matric_total_marks", 0.92, "The question asks for the matric total marks.")
        if _rule(source, r"obtained\s*marks|marks\s*obtained"):
            return hit("matric_obtained_marks", 0.92, "The question asks for the matric obtained marks.")
        if _rule(source, r"percentage|percent"):
            return hit("matric_percentage", 0.92, "The question asks for the matric percentage.")
        if _rule(source, r"cgpa|grade\s*point"):
            return hit("matric_cgpa", 0.92, "The question asks for the matric CGPA.")
        if _rule(source, r"school"):
            return hit("matric_school_name", 0.92, "The question asks for the school name.")
        if _rule(source, r"certificate"):
            return hit("matric_certificate_number", 0.9, "The question asks for a matric certificate number.")

    if _rule(context, r"intermediate|12th|senior\s*secondary|higher\s*secondary"):
        if _rule(source, r"board"):
            return hit("intermediate_board", 0.94, "The question asks for the intermediate board.")
        if _rule(source, r"stream"):
            return hit("intermediate_stream", 0.92, "The question asks for the intermediate stream.")
        if _rule(source, r"roll\s*code"):
            return hit("intermediate_roll_code", 0.92, "The question asks for the intermediate roll code.")
        if _rule(source, r"roll"):
            return hit("intermediate_roll_number", 0.93, "The question asks for the intermediate roll number.")
        if _rule(source, r"passing\s*year|year\s*of\s*passing|passing"):
            return hit("intermediate_passing_year", 0.92, "The question asks for the intermediate passing year.")
        if _rule(source, r"total\s*marks"):
            return hit("intermediate_total_marks", 0.92, "The question asks for the intermediate total marks.")
        if _rule(source, r"obtained\s*marks|marks\s*obtained"):
            return hit("intermediate_obtained_marks", 0.92, "The question asks for the intermediate obtained marks.")
        if _rule(source, r"percentage|percent"):
            return hit("intermediate_percentage", 0.92, "The question asks for the intermediate percentage.")
        if _rule(source, r"college"):
            return hit("intermediate_college_name", 0.92, "The question asks for the college name.")
        if _rule(source, r"certificate"):
            return hit("intermediate_certificate_number", 0.9, "The question asks for an intermediate certificate number.")

    if _rule(context, r"graduation|graduate|degree|bachelor|university"):
        if _rule(source, r"university"):
            return hit("graduation_university", 0.92, "The question asks for the university.")
        if _rule(source, r"degree|course|programme|program"):
            return hit("graduation_degree_name", 0.92, "The question asks for the degree name.")
        if _rule(source, r"passing\s*year|year\s*of\s*passing|passing"):
            return hit("graduation_passing_year", 0.92, "The question asks for the graduation passing year.")
        if _rule(source, r"roll"):
            return hit("graduation_roll_number", 0.92, "The question asks for the graduation roll number.")
        if _rule(source, r"cgpa|grade\s*point"):
            return hit("graduation_cgpa", 0.92, "The question asks for the graduation CGPA.")
        if _rule(source, r"percentage|percent"):
            return hit("graduation_percentage", 0.92, "The question asks for the graduation percentage.")

    if _rule(source, r"photo|photograph|passport\s*size|passport\s*photo"):
        return hit("photo_upload", 0.94, "The question asks for a photograph.")
    if _rule(source, r"signature|sign"):
        return hit("signature_upload", 0.92, "The question asks for a signature.")
    if _rule(source, r"matric.*(certificate|marksheet)|10th.*(certificate|marksheet)"):
        return hit("matric_cert_upload", 0.9, "The question asks for a matric certificate upload.")

    return ConceptMatch(
        answer_type=answer_type_for(input_type, tag),
        expected_format=expected_format,
        evidence=evidence,
        verify=verify,
        reason="The question does not match a known concept; ask before filling.",
    )


def vault_key_for(concept: Optional[str]) -> Optional[str]:
    """Return the field-registry/vault path that answers a concept."""
    if not concept:
        return None
    item = CONCEPTS.get(concept)
    if item and item.vault_key:
        return item.vault_key
    return concept


def concept_for_vault_key(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    for concept in CONCEPTS.values():
        if concept.vault_key == key or concept.key == key:
            return concept.key
    return None
