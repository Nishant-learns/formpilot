import json
import os
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

VAULT_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "candidate_vault.json")

class MatricAcademic(BaseModel):
    board: str = "CBSE"
    roll_number: str = "24108842"
    roll_code: Optional[str] = "11045"
    passing_year: str = "2019"
    total_marks: str = "500"
    obtained_marks: str = "442"
    percentage: str = "88.40"
    cgpa: Optional[str] = "8.8"
    school_name: str = "Kendriya Vidyalaya No. 1 Kankarbagh Patna"
    certificate_number: str = "CBSE/2019/MAT/88921"

class IntermediateAcademic(BaseModel):
    board: str = "BSEB"
    stream: str = "Science (PCM)"
    roll_number: str = "21030045"
    roll_code: Optional[str] = "31002"
    passing_year: str = "2021"
    total_marks: str = "500"
    obtained_marks: str = "415"
    percentage: str = "83.00"
    college_name: str = "A. N. College Patna"
    certificate_number: str = "BSEB/2021/INT/44019"

class GraduationAcademic(BaseModel):
    degree_name: str = "B.Sc Computer Science"
    university: str = "Patna University"
    passing_year: str = "2024"
    roll_number: str = "PU2021BCS042"
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
    sub_caste: str = "Kahar / Chandravanshi"
    caste_certificate_number: str = "BHTC/2023/88912"
    caste_cert_issue_date: str = "2023-04-10"
    caste_cert_authority: str = "Sub-Divisional Magistrate Patna Sadar"
    domicile_state: str = "Bihar"
    domicile_certificate_number: str = "BHDOM/2023/11044"
    is_differently_abled: str = "No"
    disability_type: str = "None"
    disability_percentage: str = "0"
    is_ex_serviceman: str = "No"
    
    # Official Identifiers & Portal Credentials
    registration_id: Optional[str] = "CREB-2026-881902"
    account_password: str = "Aman@2026#Creb"
    aadhaar_number: str = "784512963014"
    has_aadhaar: str = "Yes"
    identification_mark_1: str = "A small black mole on right side of neck"
    identification_mark_2: str = "Cut mark on left forehead near eyebrow"

    # Contact Details
    mobile: str = "9876543210"
    alternate_mobile: str = "9123456780"
    email: str = "aman.sharma.exams2026@gmail.com"
    confirm_email: str = "aman.sharma.exams2026@gmail.com"
    
    # Address Particulars
    address_line_1: str = "House No. 42, Anandpuri, West Boring Canal Road"
    address_line_2: str = "Near Shiv Mandir"
    village_town_city: str = "Patna"
    district: str = "Patna"
    state: str = "Bihar"
    pincode: str = "800001"
    
    same_as_permanent: bool = True
    present_address_line_1: str = "House No. 42, Anandpuri, West Boring Canal Road"
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
        "digilocker_id": "DL-AMANK-2024",
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
            elif fmt == "DD-MM-YYYY":
                return f"{day}-{month}-{year}"
            elif fmt == "MM/DD/YYYY":
                return f"{month}/{day}/{year}"
            elif fmt == "YYYY/MM/DD":
                return f"{year}/{month}/{day}"
            return self.dob
        except Exception:
            return self.dob

    def find_field_value(self, semantic_key: str) -> Optional[str]:
        """Deep lookup across standard and custom fields."""
        key = semantic_key.lower().replace("-", "_").replace(" ", "_")
        
        # Check direct attributes
        if hasattr(self, key):
            val = getattr(self, key)
            if isinstance(val, str):
                return val
            if isinstance(val, bool):
                return "Yes" if val else "No"
        
        # Check custom fields
        if key in self.custom_fields:
            return self.custom_fields[key]
            
        # Specific mappings
        mapping = {
            "name": self.full_name,
            "candidate_name": self.full_name,
            "applicant_name": self.full_name,
            "father": self.father_name,
            "father_name": self.father_name,
            "mother": self.mother_name,
            "mother_name": self.mother_name,
            "phone": self.mobile,
            "mobile_no": self.mobile,
            "mobile_number": self.mobile,
            "contact_no": self.mobile,
            "mail": self.email,
            "email_id": self.email,
            "email_address": self.email,
            "caste": self.category,
            "community": self.category,
            "social_category": self.category,
            "id_mark": self.identification_mark_1,
            "identification_mark": self.identification_mark_1,
            "identification_mark_2": self.identification_mark_2,
            "pin": self.pincode,
            "pin_code": self.pincode,
            "postal_code": self.pincode,
            "zip": self.pincode,
            "city": self.village_town_city,
            "town": self.village_town_city,
            "village": self.village_town_city,
            "address": self.address_line_1,
            "permanent_address": self.address_line_1,
            "aadhaar": self.aadhaar_number,
            "aadhar": self.aadhaar_number,
            "uidai": self.aadhaar_number,
            "10th_roll": self.matric.roll_number,
            "matric_roll": self.matric.roll_number,
            "10th_board": self.matric.board,
            "10th_year": self.matric.passing_year,
            "10th_marks": self.matric.obtained_marks,
            "10th_percentage": self.matric.percentage,
            "12th_roll": self.intermediate.roll_number,
            "inter_roll": self.intermediate.roll_number,
            "12th_board": self.intermediate.board,
            "12th_year": self.intermediate.passing_year,
            "12th_percentage": self.intermediate.percentage,
            "grad_roll": self.graduation.roll_number,
            "grad_university": self.graduation.university,
            "grad_percentage": self.graduation.percentage,
            "registration_id": self.registration_id or self.custom_fields.get("registration_id", "CREB-2026-881902"),
            "account_password": self.account_password,
            "password": self.account_password,
            "login_password": self.account_password,
            "login_reg_id": self.registration_id or self.custom_fields.get("registration_id", "CREB-2026-881902")
        }
        return mapping.get(key)


class VaultManager:
    """Manages loading, updating, persisting Candidate One-Vault on disk."""
    _instance = None

    def __init__(self, file_path: str = VAULT_FILE_PATH):
        self.file_path = file_path
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self.vault = self.load()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = VaultManager()
        return cls._instance

    def load(self) -> CandidateVault:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return CandidateVault(**data)
            except Exception as e:
                print(f"[VaultManager] Error reading vault, creating default: {e}")
        vault = CandidateVault()
        self.save(vault)
        return vault

    def save(self, vault: CandidateVault):
        self.vault = vault
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(vault.model_dump_json(indent=2))

    def update(self, data: Dict[str, Any]) -> CandidateVault:
        # Merge data into current vault
        current_data = self.vault.model_dump()
        for k, v in data.items():
            if k in current_data:
                current_data[k] = v
            else:
                # Add to custom_fields
                if "custom_fields" not in current_data:
                    current_data["custom_fields"] = {}
                current_data["custom_fields"][k] = str(v)
        self.vault = CandidateVault(**current_data)
        self.save(self.vault)
        return self.vault

    def add_custom_field(self, field_name: str, field_value: str) -> CandidateVault:
        self.vault.custom_fields[field_name] = field_value
        self.save(self.vault)
        return self.vault
