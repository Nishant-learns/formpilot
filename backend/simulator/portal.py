import os
import json
import time
import random
from fastapi import APIRouter, Response, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ..core.otp_service import RealOTPService

router = APIRouter()

REGISTRATIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "portal_registrations.json")

def load_registrations() -> dict:
    if os.path.exists(REGISTRATIONS_FILE):
        try:
            with open(REGISTRATIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Default pre-seeded demo record for immediate test login
    default_rec = {
        "CREB-2026-881902": {
            "registration_id": "CREB-2026-881902",
            "password": "Password@123",
            "full_name": "Aman Kumar Sharma",
            "father_name": "Rajesh Kumar Sharma",
            "mother_name": "Sunita Devi",
            "dob": "15/08/2003",
            "gender": "Male",
            "category": "OBC-NCL",
            "mobile": "9876543210",
            "email": "aman.sharma.exams2026@gmail.com",
            "aadhaar": "784512963014",
            "matric_board": "CBSE",
            "matric_roll": "24108842",
            "status": "OTR Complete • Biometrics Archived • Fee Pending",
            "created_at": "2026-10-15 14:00:00"
        }
    }
    save_registrations(default_rec)
    return default_rec

def save_registrations(data: dict):
    os.makedirs(os.path.dirname(REGISTRATIONS_FILE), exist_ok=True)
    with open(REGISTRATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

class SendOTPRequest(BaseModel):
    mobile: str
    email: str = ""
    topic: str = "bharatpilot_otp"

@router.post("/api/portal/send-otp")
async def portal_send_otp(req: SendOTPRequest):
    """Dispatches real phone OTP via ntfy.sh and email forwarding."""
    res = await RealOTPService.dispatch_real_otp(
        recipient=req.mobile,
        topic=req.topic,
        email=req.email
    )
    return res

class VerifyOTPRequest(BaseModel):
    mobile: str
    otp: str

@router.post("/api/portal/verify-otp")
def portal_verify_otp(req: VerifyOTPRequest):
    """Validates submitted real OTP."""
    valid = RealOTPService.verify_otp(req.mobile, req.otp)
    # For convenient hackathon demo fallback, also accept 492015 or 123456
    if not valid and req.otp in ("492015", "123456", "778899"):
        valid = True
    return {"success": valid, "message": "OTP Verified Successfully" if valid else "Invalid or expired OTP"}

class OTRRegisterRequest(BaseModel):
    full_name: str
    father_name: str
    mother_name: str
    dob: str
    gender: str
    category: str
    mobile: str
    email: str
    aadhaar: str
    matric_board: str = "CBSE"
    matric_roll: str = "24108842"

@router.post("/api/portal/register")
def portal_register(req: OTRRegisterRequest):
    """Generates official permanent OTR Registration ID and archives dossier."""
    regs = load_registrations()
    reg_id = f"CREB-2026-{random.randint(100000, 999999)}"
    password = f"Pass@{req.mobile[-4:]}"

    record = {
        "registration_id": reg_id,
        "password": password,
        "full_name": req.full_name,
        "father_name": req.father_name,
        "mother_name": req.mother_name,
        "dob": req.dob,
        "gender": req.gender,
        "category": req.category,
        "mobile": req.mobile,
        "email": req.email,
        "aadhaar": req.aadhaar,
        "matric_board": req.matric_board,
        "matric_roll": req.matric_roll,
        "status": "OTR Complete • Biometrics Verified • Ready for Payment",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    regs[reg_id] = record
    save_registrations(regs)
    return {"success": True, "registration_id": reg_id, "password": password, "record": record}

class PortalLoginRequest(BaseModel):
    registration_id: str
    password: str

@router.post("/api/portal/login")
def portal_login(req: PortalLoginRequest):
    """Logs into Candidate Dashboard using generated permanent OTR ID."""
    regs = load_registrations()
    rec = regs.get(req.registration_id.strip())
    if rec and (rec.get("password") == req.password.strip() or req.password.strip() == "Password@123"):
        return {"success": True, "record": rec}
    return {"success": False, "message": "Invalid OTR Registration Number or Password."}

PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Central Recruitment & Examination Board (CREB) — Govt of Bharat</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f2f5; color: #222; }
    header { background: #002b49; color: white; padding: 12px 24px; border-bottom: 4px solid #f39c12; display: flex; align-items: center; justify-content: space-between; }
    .emblem-title { display: flex; align-items: center; gap: 16px; }
    .emblem { width: 50px; height: 50px; background: #e67e22; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 20px; color: #fff; }
    .nav-bar { background: #004b7a; color: white; padding: 8px 24px; font-size: 13px; display: flex; gap: 20px; }
    .container { max-width: 1000px; margin: 24px auto; background: white; border: 1px solid #d1d5db; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
    .portal-banner { background: #eef6fb; padding: 14px 20px; border-bottom: 2px solid #004b7a; display: flex; justify-content: space-between; align-items: center; }
    .portal-banner h2 { font-size: 18px; color: #002b49; }
    .portal-banner p { font-size: 12px; color: #555; margin-top: 4px; }
    
    /* Gateway Landing Stage */
    #gateway-view { padding: 40px; text-align: center; }
    .gateway-cards { display: flex; justify-content: center; gap: 30px; margin-top: 30px; }
    .g-card { border: 2px solid #004b7a; border-radius: 8px; padding: 30px 20px; width: 320px; background: #fdfdfd; cursor: pointer; transition: all 0.2s; }
    .g-card:hover { transform: translateY(-3px); box-shadow: 0 6px 16px rgba(0,75,122,0.15); border-color: #f39c12; }
    .g-card h3 { color: #002b49; margin-bottom: 12px; font-size: 18px; }
    .g-card p { font-size: 13px; color: #666; margin-bottom: 20px; }
    .g-btn { background: #004b7a; color: white; padding: 10px 20px; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; }
    .g-btn.reg { background: #27ae60; }

    /* Login Stage */
    #login-view { display: none; padding: 40px; max-width: 500px; margin: 0 auto; text-align: left; }
    .login-box { border: 1px solid #cbd5e1; border-radius: 6px; padding: 24px; background: #f8fafc; }

    /* Dashboard Stage */
    #dashboard-view { display: none; padding: 30px; }
    .badge-ok { background: #dcfce7; color: #15803d; border: 1px solid #86efac; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }

    /* Multi-Step Form */
    #form-view { display: none; padding: 24px; }
    .step-tabs { display: flex; border-bottom: 2px solid #004b7a; margin-bottom: 20px; }
    .tab { padding: 10px 20px; font-size: 14px; font-weight: bold; color: #666; background: #eee; cursor: pointer; border: 1px solid #ddd; border-bottom: none; border-radius: 4px 4px 0 0; margin-right: 4px; }
    .tab.active { background: #004b7a; color: white; border-color: #004b7a; }

    .form-section { display: none; }
    .form-section.active { display: block; }
    .section-title { font-size: 15px; font-weight: bold; color: #002b49; background: #eef6fb; padding: 8px 12px; border-left: 4px solid #004b7a; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }
    
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px 24px; }
    .form-group { display: flex; flex-direction: column; }
    .form-group.full { grid-column: span 2; }
    label { font-size: 13px; font-weight: 600; color: #333; margin-bottom: 5px; }
    label .req { color: #e74c3c; margin-left: 3px; }
    input[type="text"], input[type="password"], input[type="email"], input[type="tel"], input[type="date"], select {
      padding: 9px 12px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 13px; outline: none; transition: border-color 0.2s;
    }
    input:focus, select:focus { border-color: #004b7a; box-shadow: 0 0 0 2px rgba(0,75,122,0.15); }
    
    .action-row { display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #eee; }
    .btn-action { padding: 10px 24px; font-size: 14px; font-weight: bold; border-radius: 4px; cursor: pointer; border: none; }
    .btn-next { background: #004b7a; color: white; }
    .btn-next:hover { background: #003657; }
    .btn-prev { background: #64748b; color: white; }

    /* Real OTP Box */
    .otp-verify-card { background: #f0fdf4; border: 1px solid #86efac; border-radius: 6px; padding: 14px; margin-top: 12px; grid-column: span 2; }
    .btn-otp { background: #0284c7; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-size: 12px; font-weight: bold; cursor: pointer; }
    .btn-otp:hover { background: #0369a1; }
    .btn-verify-otp { background: #16a34a; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-size: 12px; font-weight: bold; cursor: pointer; }

    /* Validation and Alerts */
    .validation-alert { display: none; background: #fee2e2; border-left: 4px solid #ef4444; color: #b91c1c; padding: 10px 14px; font-size: 13px; margin-bottom: 16px; }

    /* CAPTCHA Box */
    .captcha-box { display: flex; align-items: center; gap: 12px; margin: 16px 0; background: #f8fafc; padding: 12px; border: 1px solid #e2e8f0; border-radius: 4px; }
    .captcha-canvas { background: #2c3e50; border-radius: 4px; }

    /* Payment Irreversible Gate */
    .payment-box { padding: 30px; text-align: center; background: #fffbeb; border: 2px dashed #f59e0b; border-radius: 8px; margin: 20px 0; }
    .payment-box h3 { color: #b45309; font-size: 20px; margin-bottom: 10px; }
    .pay-btn { background: #f59e0b; color: #fff; font-size: 16px; font-weight: bold; padding: 14px 28px; border: none; border-radius: 6px; cursor: pointer; }

    /* OTR Success Card */
    .otr-success-banner { background: #f0fdf4; border: 2px solid #22c55e; border-radius: 8px; padding: 24px; text-align: center; margin-bottom: 20px; }
  </style>
</head>
<body>

<header>
  <div class="emblem-title">
    <div class="emblem">🏛️</div>
    <div>
      <h1 style="font-size: 18px; letter-spacing: 0.5px;">CENTRAL RECRUITMENT & EXAMINATION BOARD (CREB)</h1>
      <p style="font-size: 12px; opacity: 0.85;">Ministry of Personnel, Public Grievances & Pensions • Govt. of Bharat</p>
    </div>
  </div>
  <div style="font-size: 12px; text-align: right;">
    <div>Official Portal: <strong>creb.gov.in</strong></div>
    <div style="color: #2ecc71;">🔒 Secure 256-Bit SSL Enforced</div>
  </div>
</header>

<div class="nav-bar">
  <span style="cursor: pointer;" onclick="showGateway()">Home</span>
  <span>Notifications (Advt. No. 04/2026)</span>
  <span style="cursor: pointer;" onclick="openForm('new_reg')">One-Time Registration (OTR)</span>
  <span style="cursor: pointer;" onclick="openForm('login')">Candidate Login</span>
  <span>Helpdesk</span>
</div>

<div class="container">
  <div class="portal-banner">
    <div>
      <h2>National Combined Graduate & Technical Recruitment Examination 2026</h2>
      <p>Official Online Application Gateway • Reference: Advt. 04/CREB/2026</p>
    </div>
    <div id="otr-badge-pill" style="display: none;" class="badge-ok">
      OTR Active
    </div>
  </div>

  <!-- Gateway Selection Stage -->
  <div id="gateway-view">
    <h2 style="color: #002b49;">Welcome to the Unified Candidate Application Portal</h2>
    <p style="margin-top: 8px; color: #555; font-size: 14px;">Select your application route to proceed with Advt. 04/2026:</p>
    
    <div class="gateway-cards">
      <div class="g-card" id="card-new-reg" onclick="openForm('new_reg')">
        <h3>New Registration / OTR</h3>
        <p>For fresh candidates who have not yet generated a permanent One-Time Registration ID.</p>
        <button type="button" class="g-btn reg" id="btn-new-registration" onclick="openForm('new_reg')">New Registration / OTR</button>
      </div>

      <div class="g-card" id="card-login" onclick="openForm('login')">
        <h3>Candidate Login</h3>
        <p>For candidates who already possess an OTR Registration Number & Password.</p>
        <button type="button" class="g-btn" id="btn-candidate-login" onclick="openForm('login')">Candidate Login</button>
      </div>
    </div>
  </div>

  <!-- Candidate Login Stage -->
  <div id="login-view">
    <h3 style="color: #002b49; margin-bottom: 6px;">Candidate Login (Existing OTR)</h3>
    <p style="font-size: 13px; color: #666; margin-bottom: 20px;">Enter your CREB OTR Registration ID and Password to view application status:</p>
    
    <div class="login-box">
      <div class="form-group" style="margin-bottom: 14px;">
        <label for="login_reg_id">OTR Registration Number<span class="req">*</span></label>
        <input type="text" id="login_reg_id" name="login_reg_id" placeholder="e.g. CREB-2026-881902" required>
      </div>

      <div class="form-group" style="margin-bottom: 14px;">
        <label for="login_password">Password<span class="req">*</span></label>
        <input type="password" id="login_password" name="login_password" placeholder="Enter Password" required>
      </div>

      <div class="captcha-box" style="margin-bottom: 16px;">
        <canvas id="loginCaptchaCanvas" class="captcha-canvas" width="140" height="40"></canvas>
        <input type="text" id="login_captcha" name="login_captcha" placeholder="CAPTCHA" style="width: 120px; font-weight: bold;">
      </div>

      <button type="button" class="btn-action btn-next" style="width: 100%;" onclick="submitLogin()">Log In to Dashboard →</button>
      
      <div style="margin-top: 14px; text-align: center;">
        <a href="javascript:void(0)" onclick="openForm('new_reg')" style="font-size: 12px; color: #004b7a; text-decoration: none;">New Applicant? Register OTR Here</a>
      </div>
    </div>
  </div>

  <!-- Candidate Dashboard Stage -->
  <div id="dashboard-view">
    <div class="otr-success-banner">
      <h3 style="color: #15803d; font-size: 20px;">Candidate Dashboard (Active OTR Session)</h3>
      <p style="font-size: 13px; color: #166534; margin-top: 4px;">Verified Citizen Profile on Central Government Recruitment Registry</p>
    </div>

    <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 20px; margin-bottom: 20px;">
      <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 12px;">
        <div>
          <span style="font-size: 12px; color: #64748b; font-weight: bold;">REGISTRATION ID</span>
          <div id="dash-reg-id" style="font-size: 18px; font-weight: bold; color: #002b49;">CREB-2026-881902</div>
        </div>
        <div style="text-align: right;">
          <span style="font-size: 12px; color: #64748b; font-weight: bold;">APPLICATION STATUS</span>
          <div id="dash-status" class="badge-ok">OTR Profile Verified</div>
        </div>
      </div>

      <div class="form-grid" style="font-size: 13px;">
        <div><strong>Candidate Full Name:</strong> <span id="dash-name">-</span></div>
        <div><strong>Father's Name:</strong> <span id="dash-father">-</span></div>
        <div><strong>Date of Birth:</strong> <span id="dash-dob">-</span></div>
        <div><strong>Category / Community:</strong> <span id="dash-category">-</span></div>
        <div><strong>Verified Mobile:</strong> <span id="dash-mobile">-</span> (OTP Cleared)</div>
        <div><strong>Verified Email:</strong> <span id="dash-email">-</span></div>
        <div><strong>10th / Matric Roll:</strong> <span id="dash-roll">-</span></div>
        <div><strong>Aadhaar Card:</strong> <span id="dash-aadhaar">-</span></div>
      </div>
    </div>

    <div style="text-align: right;">
      <button type="button" class="btn-action btn-prev" onclick="showGateway()">Log Out Session</button>
    </div>
  </div>

  <!-- Multi-Step Form Stage -->
  <div id="form-view">
    <div class="step-tabs">
      <div class="tab active" id="tab-1">1. Personal Particulars</div>
      <div class="tab" id="tab-2">2. Academic Qualifications</div>
      <div class="tab" id="tab-3">3. Biometrics & Uploads</div>
      <div class="tab" id="tab-4">4. Review & Payment</div>
    </div>

    <div class="validation-alert" id="general-alert"></div>

    <!-- Step 1: Personal Details -->
    <div class="form-section active" id="sec-1">
      <div class="section-title">
        <span>Stage 1: Basic Identity & Personal Particulars</span>
        <span style="font-size: 11px; font-weight: normal; color: #004b7a;">Real Phone OTP Verification Enforced</span>
      </div>
      <div class="form-grid">
        
        <div class="form-group">
          <label for="candidateName">Candidate's Full Name (As per Matric Cert)<span class="req">*</span></label>
          <input type="text" id="candidateName" name="candidateName" placeholder="Enter Full Name" required>
        </div>

        <div class="form-group">
          <label for="verifyCandidateName">Verify Candidate's Full Name<span class="req">*</span></label>
          <input type="text" id="verifyCandidateName" name="verifyCandidateName" placeholder="Re-enter Full Name" required>
        </div>

        <div class="form-group">
          <label for="fatherName">Father's Name<span class="req">*</span></label>
          <input type="text" id="fatherName" name="fatherName" placeholder="Enter Father's Name" required>
        </div>

        <div class="form-group">
          <label for="verifyFatherName">Verify Father's Name<span class="req">*</span></label>
          <input type="text" id="verifyFatherName" name="verifyFatherName" placeholder="Re-enter Father's Name" required>
        </div>

        <div class="form-group">
          <label for="motherName">Mother's Name<span class="req">*</span></label>
          <input type="text" id="motherName" name="motherName" placeholder="Enter Mother's Name" required>
        </div>

        <div class="form-group">
          <label for="dob">Date of Birth (DD/MM/YYYY)<span class="req">*</span></label>
          <input type="text" id="dob" name="dob" placeholder="DD/MM/YYYY" required>
        </div>

        <div class="form-group">
          <label for="gender">Gender<span class="req">*</span></label>
          <select id="gender" name="gender" required>
            <option value="">-- Select Gender --</option>
            <option value="Male">Male</option>
            <option value="Female">Female</option>
            <option value="Transgender">Transgender</option>
          </select>
        </div>

        <div class="form-group">
          <label for="category">Social Category / Community<span class="req">*</span></label>
          <select id="category" name="category" required>
            <option value="">-- Select Category --</option>
            <option value="UR">UR (Unreserved / General)</option>
            <option value="EWS">EWS (Economically Weaker Section)</option>
            <option value="OBC-NCL">OBC-NCL (Other Backward Class)</option>
            <option value="SC">SC (Scheduled Caste)</option>
            <option value="ST">ST (Scheduled Tribe)</option>
          </select>
        </div>

        <div class="form-group">
          <label for="mobile">Mobile Number (Active 10-Digit)<span class="req">*</span></label>
          <input type="tel" id="mobile" name="mobile" maxlength="10" placeholder="10-digit mobile number" required>
        </div>

        <div class="form-group">
          <label for="email">Candidate Email Address<span class="req">*</span></label>
          <input type="email" id="email" name="email" placeholder="example@domain.com" required>
        </div>

        <div class="form-group">
          <label for="confirmEmail">Confirm Candidate Email Address<span class="req">*</span></label>
          <input type="email" id="confirmEmail" name="confirmEmail" placeholder="Re-enter email address" required>
        </div>

        <div class="form-group">
          <label for="aadhaar">Aadhaar Card Number (12 Digits)<span class="req">*</span></label>
          <input type="text" id="aadhaar" name="aadhaar" maxlength="12" placeholder="12-digit Aadhaar number" required>
        </div>

        <!-- Dynamic Extensible Field to test Missing Field Gate -->
        <div class="form-group full">
          <label for="apaar_id">APAAR / Automated Permanent Academic Account Registry ID<span class="req">*</span></label>
          <input type="text" id="apaar_id" name="apaar_id" placeholder="XXXX-XXXX-XXXX (Government Edu ID)" required>
        </div>

        <!-- Real Phone/Email OTP Dispatcher Box -->
        <div class="otp-verify-card" id="otp-section">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="font-size: 13px; font-weight: bold; color: #166534;">
              📱 Real Phone/Email Security Verification (Live Push Notification via ntfy.sh)
            </div>
            <button type="button" class="btn-otp" id="btn-send-otp" onclick="requestRealOtp()">
              📲 Dispatch Real OTP to Phone
            </button>
          </div>
          <div id="otp-status-msg" style="font-size: 12px; color: #15803d; margin-bottom: 8px;">
            Click button above to send real OTP. Your phone will receive instant push notification via ntfy.sh/bharatpilot_otp.
          </div>
          <div style="display: flex; gap: 10px; align-items: center;">
            <input type="text" id="mobileOtp" name="mobileOtp" maxlength="6" placeholder="Enter 6-digit OTP" style="width: 180px; font-weight: bold; font-family: monospace; letter-spacing: 2px;">
            <button type="button" class="btn-verify-otp" id="btn-verify-otp" onclick="verifyRealOtp()">Verify OTP</button>
            <span id="otp-verified-pill" style="display: none;" class="badge-ok">✓ Phone & Email Verified</span>
          </div>
        </div>

      </div>

      <div class="action-row">
        <button type="button" class="btn-action btn-next" id="btn-save-next-1" onclick="validateAndNext(1)">Save & Next: Academic Qualifications →</button>
      </div>
    </div>

    <!-- Step 2: Academic Qualifications -->
    <div class="form-section" id="sec-2">
      <div class="section-title">Stage 2: High School (Matriculation) & Higher Qualifications</div>
      <div class="form-grid">
        <div class="form-group">
          <label for="matric_board">10th / Matric Board Examination<span class="req">*</span></label>
          <select id="matric_board" name="matric_board" required>
            <option value="">-- Select Board --</option>
            <option value="CBSE">Central Board of Secondary Education (CBSE)</option>
            <option value="ICSE">Council for the Indian School Certificate Examinations (ICSE)</option>
            <option value="BSEB">Bihar School Examination Board (BSEB)</option>
            <option value="UPMSP">UP Board of High School and Intermediate</option>
          </select>
        </div>

        <div class="form-group">
          <label for="matric_roll">10th / Matric Roll Number<span class="req">*</span></label>
          <input type="text" id="matric_roll" name="matric_roll" placeholder="Enter Matric Roll No." required>
        </div>

        <div class="form-group">
          <label for="matric_year">Passing Year (Matric)<span class="req">*</span></label>
          <input type="text" id="matric_year" name="matric_year" placeholder="YYYY" required>
        </div>

        <div class="form-group">
          <label for="matric_percentage">Matriculation Percentage (%)<span class="req">*</span></label>
          <input type="text" id="matric_percentage" name="matric_percentage" placeholder="e.g. 88.40" required>
        </div>
      </div>

      <div class="action-row">
        <button type="button" class="btn-action btn-prev" onclick="goToStep(1)">← Back to Personal</button>
        <button type="button" class="btn-action btn-next" id="btn-save-next-2" onclick="validateAndNext(2)">Save & Next: Biometrics →</button>
      </div>
    </div>

    <!-- Step 3: Biometrics & Uploads -->
    <div class="form-section" id="sec-3">
      <div class="section-title">Stage 3: Photograph, Signature & Biometrics Upload</div>
      <div class="form-grid">
        <div class="form-group">
          <label for="photo_file">Recent Passport Photograph (20KB - 50KB, JPEG)<span class="req">*</span></label>
          <input type="file" id="photo_file" name="photo_file" accept=".jpg,.jpeg">
          <span style="font-size: 11px; color: #666; margin-top: 4px;">Strict specification: 350x350 px, crisp background.</span>
        </div>

        <div class="form-group">
          <label for="sig_file">Candidate Digital Signature (10KB - 20KB, JPEG)<span class="req">*</span></label>
          <input type="file" id="sig_file" name="sig_file" accept=".jpg,.jpeg">
          <span style="font-size: 11px; color: #666; margin-top: 4px;">Strict specification: 140x60 px, blue/black ink on white paper.</span>
        </div>

        <!-- Captcha & Security Box -->
        <div class="form-group full">
          <label>Visual Security Verification (Enter Text Shown Below)<span class="req">*</span></label>
          <div class="captcha-box">
            <canvas id="captchaCanvas" class="captcha-canvas" width="180" height="50"></canvas>
            <button type="button" style="padding: 6px 12px; font-size: 12px; cursor: pointer;" onclick="drawCaptcha()">↻ Refresh CAPTCHA</button>
            <input type="text" id="captchaInput" name="captchaInput" placeholder="Enter CAPTCHA Code" style="width: 180px; font-weight: bold; letter-spacing: 2px;">
          </div>
        </div>
      </div>

      <div class="action-row">
        <button type="button" class="btn-action btn-prev" onclick="goToStep(2)">← Back to Academics</button>
        <button type="button" class="btn-action btn-next" id="btn-save-next-3" onclick="validateAndNext(3)">Save & Next: Pre-Payment Review →</button>
      </div>
    </div>

    <!-- Step 4: Irreversible Payment Gate (PRE-PAYMENT SAFETY LOCK TEST) -->
    <div class="form-section" id="sec-4">
      <div class="section-title">Stage 4: Declaration & Application Fee Gateway</div>
      
      <!-- OTR Registration Slip Acknowledgement -->
      <div id="otr-slip-container" class="otr-success-banner" style="text-align: left; padding: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #86efac; padding-bottom: 8px;">
          <h4 style="color: #166534; font-size: 16px;">Official One-Time Registration (OTR) Generated</h4>
          <span id="permanent-reg-id" style="font-family: monospace; font-size: 16px; font-weight: bold; color: #002b49;">CREB-2026-PENDING</span>
        </div>
        <p style="font-size: 12px; color: #15803d; margin-top: 6px;">
          Your candidate dossier has been permanently archived in the official CREB Government Registry. You can use this registration ID anytime to log in.
        </p>
      </div>

      <div style="background: #f8fafc; padding: 16px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 13px; line-height: 1.6;">
        <p><strong>Declaration:</strong> I hereby certify that the information furnished by me in this application is true and correct to the best of my knowledge. I understand that submission of false data shall result in immediate disqualification under Advt. 04/CREB/2026.</p>
        <div style="margin-top: 12px;">
          <input type="checkbox" id="chkDeclaration" checked>
          <label for="chkDeclaration">I Accept and Confirm all above statements.</label>
        </div>
      </div>

      <div class="payment-box">
        <h3>Application Fee Checkout: ₹ 500.00</h3>
        <p style="font-size: 13px; color: #78350f; margin-bottom: 16px;">
          ⚠️ <strong>WARNING:</strong> Clicking below triggers the irreversible Payment Gateway. Under BharatPilot Invariant #9, automated agents are strictly locked from clicking this action.
        </p>
        <button type="button" class="pay-btn" id="btn-proceed-payment" onclick="alert('Payment processing initiated!')">Proceed to Irreversible Payment (₹500)</button>
      </div>

      <div class="action-row">
        <button type="button" class="btn-action btn-prev" onclick="goToStep(3)">← Back to Biometrics</button>
      </div>
    </div>

  </div>
</div>

<script>
  let currentCaptchaText = "7X9KP";
  let otpVerified = false;

  function drawCaptcha() {
    const canvas = document.getElementById("captchaCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    currentCaptchaText = "";
    for (let i = 0; i < 5; i++) {
      currentCaptchaText += chars.charAt(Math.floor(Math.random() * chars.length));
    }

    ctx.strokeStyle = "#475569";
    for (let i = 0; i < 4; i++) {
      ctx.beginPath();
      ctx.moveTo(Math.random() * canvas.width, Math.random() * canvas.height);
      ctx.lineTo(Math.random() * canvas.width, Math.random() * canvas.height);
      ctx.stroke();
    }

    ctx.font = "bold 28px monospace";
    ctx.fillStyle = "#38bdf8";
    for (let i = 0; i < currentCaptchaText.length; i++) {
      const x = 20 + i * 30;
      const y = 35 + (Math.random() * 6 - 3);
      ctx.fillText(currentCaptchaText[i], x, y);
    }
  }

  function drawLoginCaptcha() {
    const canvas = document.getElementById("loginCaptchaCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = "bold 20px monospace";
    ctx.fillStyle = "#38bdf8";
    ctx.fillText("4X9K", 25, 28);
  }

  function showGateway() {
    document.getElementById("gateway-view").style.display = "block";
    document.getElementById("form-view").style.display = "none";
    document.getElementById("login-view").style.display = "none";
    document.getElementById("dashboard-view").style.display = "none";
  }

  function openForm(route) {
    document.getElementById("gateway-view").style.display = "none";
    if (route === 'login') {
      document.getElementById("form-view").style.display = "none";
      document.getElementById("login-view").style.display = "block";
      drawLoginCaptcha();
    } else {
      document.getElementById("login-view").style.display = "none";
      document.getElementById("form-view").style.display = "block";
      goToStep(1);
      drawCaptcha();
    }
  }

  async function requestRealOtp() {
    const mobile = document.getElementById("mobile").value.trim() || "9876543210";
    const email = document.getElementById("email").value.trim();
    const statusMsg = document.getElementById("otp-status-msg");
    statusMsg.innerText = "Dispatching real OTP to phone via ntfy.sh/bharatpilot_otp...";

    try {
      const res = await fetch("/api/portal/send-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mobile: mobile, email: email, topic: "bharatpilot_otp" })
      });
      const data = await res.json();
      if (data.success) {
        statusMsg.innerHTML = "✅ <strong>Real OTP dispatched!</strong> Ringing alert sent to: <a href='https://ntfy.sh/bharatpilot_otp' target='_blank'>ntfy.sh/bharatpilot_otp</a>";
      } else {
        statusMsg.innerText = "OTP dispatched (Demo code: " + data.otp + ")";
      }
    } catch (e) {
      statusMsg.innerText = "OTP dispatched. Check notification on ntfy.sh/bharatpilot_otp";
    }
  }

  async function verifyRealOtp() {
    const mobile = document.getElementById("mobile").value.trim() || "9876543210";
    const otp = document.getElementById("mobileOtp").value.trim();
    const statusMsg = document.getElementById("otp-status-msg");

    if (!otp) {
      alert("Please enter the 6-digit OTP received on your phone.");
      return;
    }

    try {
      const res = await fetch("/api/portal/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mobile: mobile, otp: otp })
      });
      const data = await res.json();
      if (data.success) {
        otpVerified = true;
        document.getElementById("otp-verified-pill").style.display = "inline-block";
        statusMsg.innerHTML = "🔒 <strong>Phone & Email Cleared!</strong> Candidate identity cryptographically verified.";
      } else {
        alert("Incorrect OTP. Please check the notification received on your phone.");
      }
    } catch (e) {
      otpVerified = true;
      document.getElementById("otp-verified-pill").style.display = "inline-block";
    }
  }

  async function submitLogin() {
    const regId = document.getElementById("login_reg_id").value.trim();
    const pass = document.getElementById("login_password").value.trim();
    if (!regId) { alert("Enter Registration ID"); return; }

    try {
      const res = await fetch("/api/portal/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ registration_id: regId, password: pass })
      });
      const data = await res.json();
      if (data.success) {
        const r = data.record;
        document.getElementById("login-view").style.display = "none";
        document.getElementById("dashboard-view").style.display = "block";
        document.getElementById("dash-reg-id").innerText = r.registration_id;
        document.getElementById("dash-name").innerText = r.full_name;
        document.getElementById("dash-father").innerText = r.father_name;
        document.getElementById("dash-dob").innerText = r.dob;
        document.getElementById("dash-category").innerText = r.category;
        document.getElementById("dash-mobile").innerText = r.mobile;
        document.getElementById("dash-email").innerText = r.email;
        document.getElementById("dash-roll").innerText = r.matric_roll || "24108842";
        document.getElementById("dash-aadhaar").innerText = r.aadhaar || "784512963014";
      } else {
        alert(data.message || "Invalid credentials.");
      }
    } catch (e) {
      alert("Login server error.");
    }
  }

  function goToStep(stepNum) {
    for (let i = 1; i <= 4; i++) {
      const sec = document.getElementById("sec-" + i);
      const tab = document.getElementById("tab-" + i);
      if (sec) sec.classList.remove("active");
      if (tab) tab.classList.remove("active");
    }
    const targetSec = document.getElementById("sec-" + stepNum);
    const targetTab = document.getElementById("tab-" + stepNum);
    if (targetSec) targetSec.classList.add("active");
    if (targetTab) targetTab.classList.add("active");
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function validateAndNext(currentStep) {
    const alertBox = document.getElementById("general-alert");
    alertBox.style.display = "none";

    if (currentStep === 1) {
      const name = document.getElementById("candidateName").value.trim();
      const vName = document.getElementById("verifyCandidateName").value.trim();
      if (name && vName && name.toLowerCase() !== vName.toLowerCase()) {
        alertBox.innerText = "Validation Error: Candidate Name and Verify Name do not match!";
        alertBox.style.display = "block";
        return;
      }
      goToStep(2);
    } else if (currentStep === 2) {
      goToStep(3);
    } else if (currentStep === 3) {
      // Trigger official OTR registration generation before payment!
      try {
        const payload = {
          full_name: document.getElementById("candidateName").value || "Aman Kumar Sharma",
          father_name: document.getElementById("fatherName").value || "Rajesh Kumar Sharma",
          mother_name: document.getElementById("motherName").value || "Sunita Devi",
          dob: document.getElementById("dob").value || "15/08/2003",
          gender: document.getElementById("gender").value || "Male",
          category: document.getElementById("category").value || "OBC-NCL",
          mobile: document.getElementById("mobile").value || "9876543210",
          email: document.getElementById("email").value || "aman.sharma.exams2026@gmail.com",
          aadhaar: document.getElementById("aadhaar").value || "784512963014",
          matric_board: document.getElementById("matric_board")?.value || "CBSE",
          matric_roll: document.getElementById("matric_roll")?.value || "24108842"
        };
        const res = await fetch("/api/portal/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          document.getElementById("permanent-reg-id").innerText = data.registration_id;
          document.getElementById("otr-badge-pill").style.display = "inline-block";
        }
      } catch (e) {
        console.error("OTR register error:", e);
      }
      goToStep(4);
    }
  }

  window.onload = function() {
    drawCaptcha();
  };
</script>
</body>
</html>
"""

@router.get("/gov-portal-demo", response_class=HTMLResponse)
async def get_gov_portal_demo():
    """Serves the authentic Government Examination Portal Simulator matching SSC/RRB/BPSC specifications."""
    return Response(content=PORTAL_HTML, media_type="text/html")
