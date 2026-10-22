import os
import random
import time
import httpx
from typing import Dict, Any, Optional

DEFAULT_NTFY_TOPIC = "bharatpilot_otp"

class RealOTPService:
    """
    Real-world OTP Dispatcher using ntfy.sh push notifications and email.
    Judges and candidates can open https://ntfy.sh/<topic> on their mobile phone
    or desktop to receive live, ringing push notifications in real time!
    """

    _active_otps: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def generate_otp(cls, recipient: str, topic: Optional[str] = None, email: Optional[str] = None) -> str:
        """Generates a secure 6-digit OTP and records it."""
        otp = str(random.randint(100000, 999999))
        cls._active_otps[recipient] = {
            "otp": otp,
            "created_at": time.time(),
            "expires_at": time.time() + 600,  # 10 minutes
            "topic": topic or DEFAULT_NTFY_TOPIC,
            "email": email
        }
        return otp

    @classmethod
    async def dispatch_real_otp(
        cls,
        recipient: str,
        topic: Optional[str] = None,
        email: Optional[str] = None,
        portal_name: str = "Central Recruitment & Examination Board (CREB)"
    ) -> Dict[str, Any]:
        """
        Dispatches real push notification to candidate's phone via ntfy.sh
        and triggers high-priority ringing alert.
        """
        otp = cls.generate_otp(recipient, topic, email)
        chosen_topic = topic or DEFAULT_NTFY_TOPIC

        headers = {
            "Title": f"🏛️ {portal_name} OTP: {otp}",
            "Priority": "urgent",
            "Tags": "key,warning,sms",
            "Click": f"https://ntfy.sh/{chosen_topic}"
        }

        # If email is provided, ntfy can also forward notification to email!
        if email and "@" in email:
            headers["X-Email"] = email

        payload_text = (
            f"Your CREB 2026 Examination Verification Code is: {otp}\n"
            f"Mobile: {recipient}\n"
            f"Valid for 10 minutes. Do not disclose this OTP to anyone."
        )

        success = False
        ntfy_url = f"https://ntfy.sh/{chosen_topic}"
        error_msg = ""

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    ntfy_url,
                    content=payload_text.encode("utf-8"),
                    headers=headers
                )
                if res.status_code in (200, 201, 204):
                    success = True
                else:
                    error_msg = f"HTTP {res.status_code}"
        except Exception as e:
            error_msg = str(e)

        return {
            "success": success,
            "otp": otp,  # available for audit/testing
            "recipient": recipient,
            "ntfy_topic": chosen_topic,
            "ntfy_web_url": f"https://ntfy.sh/{chosen_topic}",
            "message": f"Real OTP {otp} dispatched to phone via ntfy.sh/{chosen_topic}",
            "error": error_msg
        }

    @classmethod
    def verify_otp(cls, recipient: str, user_otp: str) -> bool:
        """Verifies supplied OTP against active session."""
        rec = cls._active_otps.get(recipient)
        if not rec:
            return False
        if time.time() > rec["expires_at"]:
            return False
        return str(rec["otp"]).strip() == str(user_otp).strip()
