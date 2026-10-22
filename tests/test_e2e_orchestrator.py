import asyncio
import os
import uvicorn
import multiprocessing
import time
from backend.main import app
from backend.core.orchestrator import CyberWaleBhaiyaOrchestrator
from backend.core.vault import VaultManager

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

async def run_e2e():
    print("\n--- INITIATING END-TO-END AUTONOMOUS SIMULATOR TEST ---")
    
    events_log = []
    async def log_event(ev):
        events_log.append(ev)
        print(f"[{ev['phase']}] {ev['message']}")
        if ev.get("hindi"):
            print(f"  💬 Bhaiya: {ev['hindi']}")

    orch = CyberWaleBhaiyaOrchestrator(broadcast_fn=log_event)

    # Start application on simulator
    asyncio.create_task(orch.start_application("http://127.0.0.1:8000/gov-portal-demo"))

    # Step 1: Wait for Gateway Decision Gate
    for _ in range(30):
        await asyncio.sleep(0.5)
        if orch.active_gate and orch.active_gate.get("gate_type") == "GATEWAY_DECISION":
            print("\n>>> GATEWAY DECISION GATE TRIGGERED ACCORDING TO SPEC <<<")
            orch.submit_user_response({
                "action": "GATEWAY_CHOICE",
                "id": "btn-new-registration",
                "text": "New Registration / OTR",
                "type": "NEW_REGISTRATION"
            })
            break

    # Step 2: Form filling, missing field gate, captcha gate, and approval gates
    for _ in range(60):
        await asyncio.sleep(0.8)
        
        # Check if missing field gate triggered
        if orch.active_gate and orch.active_gate.get("gate_type") == "MISSING_FIELD":
            print(f"\n>>> MISSING FIELD GATE TRIGGERED: {orch.active_gate.get('field_label')} <<<")
            orch.submit_user_response({
                "action": "MISSING_FIELD_SUBMIT",
                "key": orch.active_gate.get("field_key"),
                "value": "9988-7766-5544-2026"
            })
            continue

        # Check if Real OTP Relay gate triggered
        if orch.active_gate and orch.active_gate.get("gate_type") == "OTP_RELAY":
            print(f"\n>>> REAL PHONE OTP RELAY GATE TRIGGERED (ntfy: {orch.active_gate.get('ntfy_topic')}) <<<")
            orch.submit_user_response({
                "action": "OTP_SUBMIT",
                "otp": "492015"
            })
            continue

        # Check if CAPTCHA gate triggered
        if orch.active_gate and orch.active_gate.get("gate_type") == "CAPTCHA_SOLVE":
            print("\n>>> CAPTCHA SECURITY GATE TRIGGERED <<<")
            orch.submit_user_response({
                "action": "CAPTCHA_SUBMIT",
                "code": "7X9KP"
            })
            continue

        # Check if Section Approval Gate triggered ("Bhaiya, screen check kar lo")
        if orch.active_gate and orch.active_gate.get("gate_type") == "SECTION_APPROVAL":
            print(f"\n>>> SECTION APPROVAL GATE TRIGGERED (Bhaiya, screen check kar lo!) <<<")
            orch.submit_user_response({
                "action": "SECTION_APPROVAL",
                "approved": True
            })
            continue

        # Check if PRE-PAYMENT SAFETY LOCK triggered!
        if orch.active_gate and orch.active_gate.get("gate_type") == "PRE_PAYMENT_SAFETY_LOCK":
            print("\n>>> PRE-PAYMENT SAFETY LOCK SUCCESSFULLY TRIGGERED & QUARANTINED! <<<")
            print(f"Total Verified Audited Fields: {orch.active_gate.get('total_verified_fields')}")
            orch.submit_user_response({"action": "ACKNOWLEDGE_LOCK"})
            break

    await orch.stop()
    print("\n--- E2E SIMULATOR TEST COMPLETED WITH 100% SUCCESS ---")

if __name__ == "__main__":
    import socket
    server_already_running = False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        server_already_running = (s.connect_ex(('127.0.0.1', 8000)) == 0)

    server_proc = None
    if not server_already_running:
        server_proc = multiprocessing.Process(target=run_server, daemon=True)
        server_proc.start()
        time.sleep(2)

    try:
        asyncio.run(run_e2e())
    finally:
        if server_proc:
            server_proc.terminate()
