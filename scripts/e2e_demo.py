"""Drive the FormPilot practice portal through every human checkpoint.

Start the app first:

    ./run.sh

Then, in another terminal:

    python scripts/e2e_demo.py              # new registration flow
    python scripts/e2e_demo.py --login      # returning-candidate flow

The script uses the same orchestrator as the web UI. It stops before payment
and never clicks the demo payment button.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core import settings
from backend.core.orchestrator import FormPilotOrchestrator


def _sample_upload(kind: str) -> Path:
    """Create a small valid JPEG for the practice portal's file inputs."""
    from PIL import Image, ImageDraw

    path = Path(tempfile.gettempdir()) / f"formpilot-e2e-{kind}.jpg"
    image = Image.new("RGB", (600, 800), (246, 247, 249))
    draw = ImageDraw.Draw(image)
    draw.rectangle((36, 36, 564, 764), outline=(20, 72, 120), width=5)
    draw.text((70, 80), "FormPilot practice upload", fill=(20, 40, 60))
    draw.text((70, 110), f"Field: {kind}", fill=(60, 80, 100))
    draw.text((70, 140), "Demo file - not a real document", fill=(120, 60, 60))
    image.save(path, "JPEG", quality=88)
    return path


async def run(target: str, login: bool) -> int:
    orchestrator = FormPilotOrchestrator()
    task = asyncio.create_task(orchestrator.start_application(target))
    deadline = time.time() + 240
    last_gate = None
    responded = False
    result = 1

    try:
        while time.time() < deadline:
            state = orchestrator.get_state()
            gate = state.get("active_gate")
            if gate:
                signature = (
                    gate.get("gate_type"),
                    gate.get("title"),
                    gate.get("field_key"),
                    gate.get("section_number"),
                )
                if signature != last_gate:
                    print(f"CHECKPOINT {gate.get('gate_type')}: {gate.get('title')}", flush=True)
                    last_gate = signature
                    responded = False

                if not responded:
                    gate_type = gate.get("gate_type")
                    if gate_type == "GATEWAY_DECISION":
                        options = gate.get("options") or []
                        wanted = "LOGIN" if login else "NEW_REGISTRATION"
                        choice = next(
                            (option for option in options if option.get("type") == wanted),
                            options[0] if options else {},
                        )
                        orchestrator.submit_user_response(
                            {
                                "action": "GATEWAY_CHOICE",
                                "id": choice.get("id"),
                                "text": choice.get("text"),
                            }
                        )
                    elif gate_type == "MISSING_FIELD":
                        orchestrator.submit_user_response(
                            {
                                "action": "MISSING_FIELD_SUBMIT",
                                "key": gate.get("field_key"),
                                "value": "DEMO-0000-0000",
                            }
                        )
                    elif gate_type == "OTP_RELAY":
                        orchestrator.submit_user_response(
                            {"action": "OTP_SUBMIT", "otp": settings.DEMO_OTP}
                        )
                    elif gate_type == "CAPTCHA_SOLVE":
                        code = "4X9K" if login else "7X9KP"
                        orchestrator.submit_user_response(
                            {"action": "CAPTCHA_SUBMIT", "code": code}
                        )
                    elif gate_type in {"FILE_UPLOAD", "LIVE_PHOTO"}:
                        field_key = gate.get("field_key") or "photo_upload"
                        upload = _sample_upload(field_key)
                        result = await orchestrator.attach_upload(str(upload), field_key)
                        print(
                            f"UPLOAD {field_key}: {result.get('message')}",
                            flush=True,
                        )
                        orchestrator.submit_user_response(
                            {
                                "action": "UPLOAD_COMPLETE",
                                "field_key": field_key,
                            }
                        )
                    elif gate_type == "LIVE_HANDOFF":
                        print(
                            f"LIVE HANDOFF REQUIRED: {gate.get('description')}",
                            flush=True,
                        )
                        result = 1
                        break
                    elif gate_type == "SECTION_APPROVAL":
                        orchestrator.submit_user_response(
                            {"action": "SECTION_APPROVAL", "approved": True}
                        )
                    elif gate_type == "PRE_PAYMENT_SAFETY_LOCK":
                        audit = gate.get("audit_diff") or []
                        matched = sum(1 for row in audit if row.get("status") == "MATCH")
                        label = (
                            "STOPPED BEFORE SUBMISSION"
                            if gate.get("final_action") == "submission"
                            else "STOPPED BEFORE PAYMENT"
                        )
                        print(
                            f"{label}: {matched}/{len(audit)} fields match.",
                            flush=True,
                        )
                        print(f"Audit run: {gate.get('run_id')}", flush=True)
                        result = 0
                        responded = True
                        break
                    elif gate_type == "ERROR_DIAGNOSIS":
                        print(f"PORTAL ERROR: {gate.get('error_text')}", flush=True)
                        break
                    else:
                        print(f"UNHANDLED CHECKPOINT: {gate_type}", flush=True)
                        break
                    responded = True

            if state.get("state") in {"AWAITING_PAYMENT", "FAILED", "STOPPED", "DONE"} and not gate:
                if state.get("state") in {"AWAITING_PAYMENT", "DONE"}:
                    result = 0
                print(f"FINAL STATE: {state.get('state')}", flush=True)
                if state.get("last_error"):
                    print(f"ERROR: {state.get('last_error')}", flush=True)
                break

            await asyncio.sleep(0.4)
        else:
            print(f"TIMEOUT: {orchestrator.get_state().get('state')}", flush=True)
    finally:
        state = orchestrator.get_state()
        print(
            "SUMMARY:",
            {
                "state": state.get("state"),
                "mode": state.get("mode"),
                "section": state.get("current_section"),
                "filled": len(state.get("filled_audit") or []),
                "run_id": state.get("run_id"),
            },
            flush=True,
        )
        # Let the run loop finish its final event before closing the browser,
        # so a handover screenshot is not cut off mid-flight.
        try:
            await asyncio.wait_for(task, timeout=8)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        except Exception:
            pass
        try:
            await orchestrator.stop()
        except Exception:
            pass

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "target",
        nargs="?",
        default="http://127.0.0.1:8000/gov-portal-demo",
        help="Practice portal URL",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Exercise the returning-candidate login route instead of a new registration",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.target, args.login)))


if __name__ == "__main__":
    main()
