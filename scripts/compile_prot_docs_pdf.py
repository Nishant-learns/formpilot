import os
import shutil
import weasyprint

def compile_docs():
    hackathon_dir = "/home/nishant/Desktop/Desktop/hackthon"
    workspace_dir = "/home/nishant/Documents/antigravity/blissful-brahmagupta"

    prot_docs_hackathon = os.path.join(hackathon_dir, "prot_docs")
    prot_docs_workspace = os.path.join(workspace_dir, "prot_docs")

    os.makedirs(prot_docs_hackathon, exist_ok=True)
    os.makedirs(prot_docs_workspace, exist_ok=True)

    images = [
        ("/tmp/test_filling.png", "01_autonomous_form_fill_and_otp_checkpoint.png"),
        ("/tmp/test_live_gate.png", "02_human_checkpoint_gateway_decision.png"),
        ("/tmp/test_idle.png", "03_candidate_cockpit_portal_launcher.png"),
        ("/tmp/test_gov_portal.png", "04_public_recruitment_portal_simulator.png"),
        ("/tmp/test_run_report.png", "05_forensic_run_audit_report.png")
    ]

    saved_paths = []
    for src, fname in images:
        dst1 = os.path.join(prot_docs_hackathon, fname)
        dst2 = os.path.join(prot_docs_workspace, fname)
        shutil.copy2(src, dst1)
        shutil.copy2(src, dst2)
        saved_paths.append((dst1, fname))
        print(f"Saved: {dst1}")

    # Build PDF with WeasyPrint
    img1 = os.path.abspath(os.path.join(prot_docs_hackathon, "01_autonomous_form_fill_and_otp_checkpoint.png"))
    img2 = os.path.abspath(os.path.join(prot_docs_hackathon, "02_human_checkpoint_gateway_decision.png"))
    img3 = os.path.abspath(os.path.join(prot_docs_hackathon, "03_candidate_cockpit_portal_launcher.png"))
    img4 = os.path.abspath(os.path.join(prot_docs_hackathon, "04_public_recruitment_portal_simulator.png"))
    img5 = os.path.abspath(os.path.join(prot_docs_hackathon, "05_forensic_run_audit_report.png"))

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
  
  @page {{
    size: 297mm 210mm; /* A4 Landscape */
    margin: 10mm 12mm 10mm 12mm;
  }}

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    font-family: 'Plus Jakarta Sans', sans-serif;
    background-color: #0B132B;
    color: #F8FAFC;
    -webkit-print-color-adjust: exact;
  }}

  .page {{
    page-break-after: always;
    height: 190mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}

  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 2px solid #1E293B;
    padding-bottom: 4mm;
    margin-bottom: 4mm;
  }}

  .badge {{
    display: inline-block;
    padding: 3px 8px;
    background: rgba(56, 189, 248, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.35);
    color: #38BDF8;
    border-radius: 4px;
    font-size: 8pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 2px;
  }}

  .title {{
    font-size: 15pt;
    font-weight: 800;
    color: #FFFFFF;
  }}

  .desc {{
    font-size: 9pt;
    color: #94A3B8;
    margin-top: 1px;
    line-height: 1.35;
    max-width: 220mm;
  }}

  .page-num {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 9pt;
    color: #64748B;
    background: #0F172A;
    border: 1px solid #1E293B;
    padding: 3px 8px;
    border-radius: 4px;
  }}

  .image-container {{
    flex: 1;
    display: flex;
    justify-content: center;
    align-items: center;
    background: #060B18;
    border: 1px solid #1E293B;
    border-radius: 8px;
    padding: 3mm;
    overflow: hidden;
  }}

  .screenshot {{
    max-width: 100%;
    max-height: 140mm;
    object-fit: contain;
    border-radius: 4px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  }}

  .footer {{
    display: flex;
    justify-content: space-between;
    font-size: 8pt;
    color: #64748B;
    border-top: 1px solid #1E293B;
    padding-top: 3mm;
    margin-top: 3mm;
  }}
</style>
</head>
<body>

<!-- PAGE 1: AUTONOMOUS FILL & OTP CHECKPOINT -->
<div class="page">
  <div class="header">
    <div>
      <span class="badge">Evidence 01 · Live Autonomous Execution</span>
      <div class="title">Autonomous Multi-Field Filling with Docked Human OTP Checkpoint</div>
      <div class="desc">
        Demonstrates FormPilot automatically filling 13 verified fields (Candidate Name, Father's Name, Mother's Name, DOB, Category, APAAR ID, Matric marks) into a public recruitment portal while synchronizing dual-verification inputs. Automation automatically halts and docks an interactive checkpoint when the portal requires a mobile OTP.
      </div>
    </div>
    <div class="page-num">01 / 05</div>
  </div>
  <div class="image-container">
    <img src="file://{img1}" class="screenshot" alt="Autonomous Form Fill & OTP Checkpoint" />
  </div>
  <div class="footer">
    <span>FormPilot Prototype & Operational Evidence Dossier</span>
    <span>Figure 1: Live Playwright/CDP Execution & Verification Checkpoint</span>
  </div>
</div>

<!-- PAGE 2: GATEWAY DECISION CHECKPOINT -->
<div class="page">
  <div class="header">
    <div>
      <span class="badge">Evidence 02 · Human-in-the-Loop Safety</span>
      <div class="title">Explicit Gateway Decision Checkpoint (No Guessing Policy)</div>
      <div class="desc">
        Demonstrates FormPilot refusing to guess candidate intentions. When a recruitment portal offers dual entry pathways (New Registration / OTR vs Returning Candidate Login), FormPilot freezes automation and presents a clear bilingual choice modal while keeping the live browser accessible.
      </div>
    </div>
    <div class="page-num">02 / 05</div>
  </div>
  <div class="image-container">
    <img src="file://{img2}" class="screenshot" alt="Human Gateway Decision Modal" />
  </div>
  <div class="footer">
    <span>FormPilot Prototype & Operational Evidence Dossier</span>
    <span>Figure 2: Human-in-the-Loop Gateway Selection & Takeover Protocol</span>
  </div>
</div>

<!-- PAGE 3: CANDIDATE COCKPIT & LAUNCHER -->
<div class="page">
  <div class="header">
    <div>
      <span class="badge">Evidence 03 · Candidate Workspace</span>
      <div class="title">Candidate Cockpit: Portal Launcher, Vault Readiness & Cognitive Stream</div>
      <div class="desc">
        The applicant dashboard showing 100% profile readiness, verified candidate vault credentials, instant access to official recruitment boards (Railway RRB, SSC, State PSCs, UPSC), and the built-in empathetic chat assistant.
      </div>
    </div>
    <div class="page-num">03 / 05</div>
  </div>
  <div class="image-container">
    <img src="file://{img3}" class="screenshot" alt="Candidate Cockpit Dashboard" />
  </div>
  <div class="footer">
    <span>FormPilot Prototype & Operational Evidence Dossier</span>
    <span>Figure 3: Candidate Control Center with 100% Profile Vault Readiness</span>
  </div>
</div>

<!-- PAGE 4: PORTAL SIMULATOR GATEWAY -->
<div class="page">
  <div class="header">
    <div>
      <span class="badge">Evidence 04 · Practice & Simulation Suite</span>
      <div class="title">End-to-End Government Recruitment Portal Practice Environment</div>
      <div class="desc">
        A realistic, isolated simulation environment mirroring the architectural layout, authentication flows, and security constraints of Indian public recruitment portals. Allows testing full candidate journeys without touching live government infrastructure.
      </div>
    </div>
    <div class="page-num">04 / 05</div>
  </div>
  <div class="image-container">
    <img src="file://{img4}" class="screenshot" alt="Public Recruitment Portal Simulator" />
  </div>
  <div class="footer">
    <span>FormPilot Prototype & Operational Evidence Dossier</span>
    <span>Figure 4: Realistic Multi-Step Public Recruitment Portal Practice Suite</span>
  </div>
</div>

<!-- PAGE 5: FORENSIC RUN AUDIT LEDGER -->
<div class="page">
  <div class="header">
    <div>
      <span class="badge">Evidence 05 · Complete Auditability</span>
      <div class="title">Forensic Run Ledger: Field Commit Verdicts, Token Metering & Timeline</div>
      <div class="desc">
        Every run generates a persistent, tamper-evident audit report. Shows verified field-commit classifications (checking if portal retained values), precise human-attended vs active-work time budgets, token usage, and security boundary timeline for complete transparency.
      </div>
    </div>
    <div class="page-num">05 / 05</div>
  </div>
  <div class="image-container">
    <img src="file://{img5}" class="screenshot" alt="Forensic Run Audit Report" />
  </div>
  <div class="footer">
    <span>FormPilot Prototype & Operational Evidence Dossier</span>
    <span>Figure 5: Tamper-Evident Run Audit Report & Field Verification Ledger</span>
  </div>
</div>

</body>
</html>
"""

    pdf_out_hackathon = os.path.join(hackathon_dir, "prototype.pdf")
    pdf_out_workspace = os.path.join(workspace_dir, "prototype.pdf")

    print(f"Generating combined PDF via WeasyPrint at {pdf_out_hackathon}...")
    weasyprint.HTML(string=html).write_pdf(pdf_out_hackathon)
    shutil.copy2(pdf_out_hackathon, pdf_out_workspace)

    print(f"Successfully generated prototype.pdf ({os.path.getsize(pdf_out_hackathon)/1024:.1f} KB)")

if __name__ == "__main__":
    compile_docs()
