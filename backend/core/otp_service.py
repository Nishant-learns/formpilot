from __future__ import annotations

import secrets
import time
from typing import Any, Dict, Optional

import httpx

from . import settings


class RealOTPService:
    """Sends a verification code over the configured ntfy.sh topic.

    This is a demo-friendly notification relay, not an SMS gateway.  In
    production, replace it with an SMS/email provider and never return the
    code to the browser.
    """

    _active_otps: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def generate_otp(cls, recipient: str, topic: Optional[str] = None, email: Optional[str] = None) -> str:
        otp = f"{secrets.randbelow(1_000_000):06d}"
        cls._active_otps[recipient] = {
            "otp": otp,
            "created_at": time.time(),
            "expires_at": time.time() + settings.OTP_TTL_SECONDS,
            "topic": topic or settings.NTFY_TOPIC,
            "email": email,
        }
        return otp

    @classmethod
    async def dispatch_real_otp(
        cls,
        recipient: str,
        topic: Optional[str] = None,
        email: Optional[str] = None,
        portal_name: str = "FormPilot Practice Portal",
    ) -> Dict[str, Any]:
        chosen_topic = (topic or settings.NTFY_TOPIC).strip()
        otp = cls.generate_otp(recipient, chosen_topic, email)
        ntfy_url = f"https://ntfy.sh/{chosen_topic}"

        headers = {
            "Title": f"FormPilot verification code: {otp}",
            "Priority": "urgent",
            "Tags": "key,warning",
            "Click": ntfy_url,
        }
        if email and "@" in email:
            headers["X-Email"] = email

        payload_text = (
            f"Your FormPilot practice verification code is: {otp}\n"
            f"Valid for {max(1, settings.OTP_TTL_SECONDS // 60)} minutes. "
            "Do not share this code with anyone."
        )

        success = False
        error_msg = ""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    ntfy_url,
                    content=payload_text.encode("utf-8"),
                    headers=headers,
                )
            if response.status_code in (200, 201, 204):
                success = True
            else:
                error_msg = f"Notification service returned HTTP {response.status_code}."
        except Exception as exc:
            error_msg = str(exc)

        result: Dict[str, Any] = {
            "success": success,
            "recipient": recipient,
            "ntfy_topic": chosen_topic,
            "ntfy_web_url": ntfy_url,
            "message": "Verification code sent." if success else "Could not send the verification code.",
            "error": error_msg,
        }
        # Only the practice portal exposes the code in the response.  A real
        # portal must never do this.
        if settings.DEMO_MODE:
            result["demo_otp"] = otp
        return result

    @classmethod
    def verify_otp(cls, recipient: str, user_otp: str) -> bool:
        if settings.DEMO_MODE and str(user_otp).strip() == settings.DEMO_OTP:
            return True
        record = cls._active_otps.get(recipient)
        if not record:
            return False
        if time.time() > record["expires_at"]:
            return False
        return secrets.compare_digest(str(record["otp"]), str(user_otp).strip())
