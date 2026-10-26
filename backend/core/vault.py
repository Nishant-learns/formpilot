import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field

from . import field_registry
from .vault_crypto import VaultCipher, VaultCryptoError, cipher_from_env, decode_envelope


def _default_vault_path() -> Path:
    # Resolve at call time so tests can point FORMPILOT_DATA_DIR at tmp_path.
    data_dir = Path(os.getenv("FORMPILOT_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
    return data_dir / "candidate_vault.json"


class MatricAcademic(BaseModel):
    board: str = "CBSE"
    roll_number: str = "24108842"
    roll_code: Optional[str] = "11045"
    passing_year: str = "2019"
    total_marks: str = "500"
    obtained_marks: str = "442"
    percentage: str = "88.40"
    cgpa: Optional[str] = "8.8"
    school_name: str = "Demo Public School, Patna"
    certificate_number: str = "DEMO/CBSE/2019/001"


class IntermediateAcademic(BaseModel):
    board: str = "BSEB"
    stream: str = "Science (PCM)"
    roll_number: str = "21030045"
    roll_code: Optional[str] = "31002"
    passing_year: str = "2021"
    total_marks: str = "500"
    obtained_marks: str = "415"
    percentage: str = "83.00"
    college_name: str = "Demo College, Patna"
    certificate_number: str = "DEMO/BSEB/2021/001"


class GraduationAcademic(BaseModel):
    degree_name: str = "B.Sc Computer Science"
    university: str = "Demo University"
    passing_year: str = "2024"
    roll_number: str = "DEMO-PU-2021-042"
    cgpa: str = "8.4"
    percentage: str = "79.80"


class CandidateVault(BaseModel):
    # Personal Identity
    full_name: str = "Aman Kumar Sharma"
    verify_full_name: str = "Aman Kumar Sharma"
    father_name: str = "Rajesh Kumar Sharma"
    verify_father_name: str = "Rajesh Kumar Sharma"
    mother_name: str = "Sunita Devi"
    verify_mother_name: str = "Sunita Devi"
    dob: str = "2003-08-15"  # YYYY-MM-DD
    gender: str = "Male"
    marital_status: str = "Unmarried"
    religion: str = "Hindu"
    nationality: str = "Indian"

    # Reservation & Domicile
    category: str = "OBC-NCL"  # UR, EWS, OBC-NCL, SC, ST
    sub_caste: str = "Demo Community"
    caste_certificate_number: str = "DEMO-CASTE-2023-001"
    caste_cert_issue_date: str = "2023-04-10"
    caste_cert_authority: str = "Demo Certifying Authority"
    domicile_state: str = "Bihar"
    domicile_certificate_number: str = "DEMO-DOM-2023-001"
    is_differently_abled: str = "No"
    disability_type: str = "None"
    disability_percentage: str = "0"
    is_ex_serviceman: str = "No"

    # Official Identifiers & Portal Credentials
    registration_id: Optional[str] = "FP-2026-881902"
    account_password: str = "Practice@123"
    aadhaar_number: str = "123456789012"
    has_aadhaar: str = "Yes"
    identification_mark_1: str = "Small mole on the right side of the neck"
    identification_mark_2: str = "Mark on the left forehead"

    # Contact Details
    mobile: str = "9876543210"
    alternate_mobile: str = "9123456780"
    email: str = "demo.candidate@example.com"
    confirm_email: str = "demo.candidate@example.com"

    # Address Particulars
    address_line_1: str = "House 12, Demo Nagar"
    address_line_2: str = "Near Demo Park"
    village_town_city: str = "Patna"
    district: str = "Patna"
    state: str = "Bihar"
    pincode: str = "800001"

    same_as_permanent: bool = True
    present_address_line_1: str = "House 12, Demo Nagar"
    present_district: str = "Patna"
    present_state: str = "Bihar"
    present_pincode: str = "800001"

    # Academic Records
    matric: MatricAcademic = Field(default_factory=MatricAcademic)
    intermediate: IntermediateAcademic = Field(default_factory=IntermediateAcademic)
    graduation: GraduationAcademic = Field(default_factory=GraduationAcademic)

    # Document & Biometric references
    photo_path: Optional[str] = "uploads/candidate_photo.jpg"
    signature_path: Optional[str] = "uploads/candidate_signature.jpg"
    matric_cert_path: Optional[str] = "uploads/matric_marksheet.pdf"

    # Extensible Dynamic Fields (APAAR, ABC, DigiLocker, Height, etc.)
    custom_fields: Dict[str, str] = Field(default_factory=lambda: {
        "apaar_id": "1234-5678-9012",
        "digilocker_id": "DL-DEMO-0001",
        "height_cm": "172",
        "chest_cm": "84",
        "mother_tongue": "Hindi",
        "employment_status": "Unemployed",
        "criminal_case_pending": "No",
        "debarred_from_exam": "No"
    })

    def get_formatted_dob(self, fmt: str = "YYYY-MM-DD") -> str:
        """Convert YYYY-MM-DD into various government portal date formats."""
        try:
            parts = self.dob.split("-")
            year, month, day = parts[0], parts[1], parts[2]
            if fmt == "DD/MM/YYYY":
                return f"{day}/{month}/{year}"
            if fmt == "DD-MM-YYYY":
                return f"{day}-{month}-{year}"
            if fmt == "MM/DD/YYYY":
                return f"{month}/{day}/{year}"
            if fmt == "YYYY/MM/DD":
                return f"{year}/{month}/{day}"
            return self.dob
        except Exception:
            return self.dob

    def find_field_value(self, semantic_key: str) -> Optional[str]:
        """Resolve a semantic field key against this vault.

        Delegates to the field registry so the DOM classifier and the vault
        cannot drift apart again.
        """
        return field_registry.resolve_value(self, semantic_key)

    def public_dict(self, mask_sensitive: bool = False) -> Dict[str, Any]:
        data = self.model_dump()
        if mask_sensitive:
            for key, spec in field_registry.FIELD_SPECS.items():
                if not spec.sensitive:
                    continue
                if "." not in spec.path and spec.path in data:
                    data[spec.path] = field_registry.mask_value(key, data.get(spec.path))
            data["custom_fields"] = {
                key: field_registry.mask_value(key, value)
                for key, value in data.get("custom_fields", {}).items()
            }
        return data


class VaultManager:
    """Manages loading, updating, persisting Candidate One-Vault on disk."""
    _instance = None
    _instance_path: Optional[str] = None

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = Path(file_path) if file_path else _default_vault_path()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher: Optional[VaultCipher] = cipher_from_env()
        self.vault = self.load()

    @classmethod
    def get_instance(cls):
        path = str(_default_vault_path())
        if cls._instance is None or cls._instance_path != path:
            cls._instance = VaultManager(path)
            cls._instance_path = path
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None
        cls._instance_path = None

    def load(self) -> CandidateVault:
        if self.file_path.exists():
            try:
                raw = self.file_path.read_text(encoding="utf-8")
                is_encrypted, payload = decode_envelope(raw)
                if is_encrypted:
                    if not self._cipher:
                        raise VaultCryptoError(
                            "Vault is encrypted but FORMPILOT_VAULT_KEY is not set."
                        )
                    plaintext = self._cipher.decrypt_bytes(payload)  # type: ignore[arg-type]
                    return CandidateVault(**json.loads(plaintext))
                return CandidateVault(**json.loads(raw))
            except VaultCryptoError:
                raise
            except Exception as exc:
                print(f"[VaultManager] Error reading vault, creating default: {exc}")
        vault = CandidateVault()
        self.save(vault)
        return vault

    def save(self, vault: CandidateVault):
        self.vault = vault
        plaintext = vault.model_dump_json(indent=2).encode("utf-8")
        if self._cipher:
            envelope = self._cipher.encrypt_bytes(plaintext)
            output = json.dumps(envelope, indent=2).encode("utf-8")
        else:
            output = plaintext

        # Atomic write: a half-written vault is worse than no write at all.
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.file_path.name}.", suffix=".tmp", dir=str(self.file_path.parent)
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(output)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.file_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def update(self, data: Dict[str, Any]) -> CandidateVault:
        current_data = self.vault.model_dump()
        for key, value in data.items():
            if key == "custom_fields" and isinstance(value, dict):
                merged = dict(current_data.get("custom_fields", {}))
                merged.update({str(k): str(v) for k, v in value.items()})
                current_data["custom_fields"] = merged
            elif key in current_data:
                current_data[key] = value
            else:
                current_data.setdefault("custom_fields", {})[str(key)] = str(value)
        self.vault = CandidateVault(**current_data)
        self.save(self.vault)
        return self.vault

    def add_custom_field(self, field_name: str, field_value: str) -> CandidateVault:
        key = field_registry.normalize_key(field_name)
        self.vault.custom_fields[key] = str(field_value)
        self.save(self.vault)
        return self.vault

    def set_semantic_field(self, semantic_key: str, value: str) -> CandidateVault:
        """Write a value to the canonical location for a semantic key.

        This handles both top-level fields (`full_name`) and nested academic
        records (`matric.roll_number`) instead of dumping everything into
        `custom_fields`.
        """
        spec = field_registry.spec_for(semantic_key)
        path = spec.path if spec else field_registry.canonical_key(semantic_key)
        if path.startswith("custom_fields."):
            self.vault.custom_fields[path.split(".", 1)[1]] = str(value)
            self.save(self.vault)
            return self.vault

        parts = path.split(".")
        if len(parts) == 1:
            if hasattr(self.vault, parts[0]):
                setattr(self.vault, parts[0], value)
            else:
                self.vault.custom_fields[parts[0]] = str(value)
            self.save(self.vault)
            return self.vault

        target: Any = self.vault
        for part in parts[:-1]:
            target = getattr(target, part, None)
            if target is None:
                raise ValueError(f"Cannot resolve nested field path: {path}")
        setattr(target, parts[-1], value)
        self.save(self.vault)
        return self.vault

    def reset_defaults(self) -> CandidateVault:
        self.vault = CandidateVault()
        self.save(self.vault)
        return self.vault
