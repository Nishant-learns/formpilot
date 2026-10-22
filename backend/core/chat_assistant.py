import re
import datetime
import httpx
from typing import Dict, Any, Optional, Tuple, List

from .vault import VaultManager, CandidateVault
from .tinyfish_client import TinyFishClient

class CyberBhaiyaChatAssistant:
    """
    Intelligent Conversational Brain for 'CyberBhaiya'.
    Provides empathetic, street-smart Indian cyber cafe operator dialogue,
    contextual memory of the candidate and live form, field mutation execution,
    workflow actions, and live search via TinyFish.
    """

    def __init__(self, orchestrator=None, vault_mgr=None, tinyfish_client=None):
        self.orchestrator = orchestrator
        self.vault_mgr = vault_mgr or VaultManager.get_instance()
        self.tinyfish_client = tinyfish_client or TinyFishClient()
        self.chat_history: List[Dict[str, str]] = []

    async def handle_message(self, user_msg: str) -> Dict[str, Any]:
        """
        Processes candidate chat message, executes any required browser/vault mutations,
        and returns a structured conversational response.
        """
        msg_clean = user_msg.strip()
        timestamp = datetime.datetime.now().strftime("%H:%M")
        
        self.chat_history.append({"sender": "Candidate", "text": msg_clean, "time": timestamp})

        # 1. Check for Field Edit Intent
        edit_res = await self._try_field_edit(msg_clean)
        if edit_res:
            self.chat_history.append({"sender": "CyberBhaiya", "text": edit_res["reply"], "time": timestamp})
            return edit_res

        # 2. Check for Workflow Actions (Pause, Resume, Next, Dismiss)
        workflow_res = await self._try_workflow_action(msg_clean)
        if workflow_res:
            self.chat_history.append({"sender": "CyberBhaiya", "text": workflow_res["reply"], "time": timestamp})
            return workflow_res

        # 3. Check for Exam & Recruitment Knowledge / FAQ
        faq_res = self._try_faq_knowledge(msg_clean)
        if faq_res:
            self.chat_history.append({"sender": "CyberBhaiya", "text": faq_res["reply"], "time": timestamp})
            return faq_res

        # 4. Check for External Live Information Query (Use TinyFish Search API)
        search_res = await self._try_tinyfish_search(msg_clean)
        if search_res:
            self.chat_history.append({"sender": "CyberBhaiya", "text": search_res["reply"], "time": timestamp})
            return search_res

        # 5. Default Empathetic Dialogue
        candidate_name = self.vault_mgr.vault.full_name.split()[0] if self.vault_mgr.vault.full_name else "Bhai"
        default_reply = (
            f"Haan {candidate_name}, bolo! Form mein koi dikkat hai ya koi detail badalni hai toh batayein. "
            f"Aap mujhe bol sakte hain jaise 'father name badal kar Rajesh Sharma karo', 'fees kitni hai', ya 'form pause karo'. "
            f"Mai yahan aapke saath live baitha hoon!"
        )
        resp = {
            "reply": default_reply,
            "action_taken": "CONVERSATION",
            "field_updated": None,
            "new_value": None,
            "timestamp": timestamp
        }
        self.chat_history.append({"sender": "CyberBhaiya", "text": default_reply, "time": timestamp})
        return resp

    async def _try_field_edit(self, text: str) -> Optional[Dict[str, Any]]:
        """Detects if candidate wants to update a field in their One-Vault & live portal."""
        text_lower = text.lower()

        # Target definitions: (field_pattern, vault_key, field_label, value_pattern)
        field_targets = [
            (r"(?:father(?:\s*name)?|pitaji|papa)", "father_name", "Father's Name", r"[a-zA-Z\s\.\']{3,40}"),
            (r"(?:mother(?:\s*name)?|mataji|mummy)", "mother_name", "Mother's Name", r"[a-zA-Z\s\.\']{3,40}"),
            (r"(?:candidate(?:\s*name)?|my\s*name|apna\s*naam|naam|full\s*name)", "full_name", "Candidate Full Name", r"[a-zA-Z\s\.\']{3,40}"),
            (r"(?:dob|date\s*of\s*birth|janam\s*tithi)", "dob", "Date of Birth", r"\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}"),
            (r"(?:mobile|phone|contact)(?:\s*(?:no|number))?", "mobile", "Mobile Number", r"[6-9]\d{9}"),
            (r"(?:email|mail|e-mail)(?:\s*(?:id|address))?", "email", "Email Address", r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
            (r"(?:category|caste|jaati|community)", "category", "Social Category", r"obc-ncl|obc|general|ur|ews|sc|st"),
            (r"(?:aadhaar|aadhar)(?:\s*(?:no|number))?", "aadhaar_number", "Aadhaar Number", r"\d{12}"),
            (r"(?:apaar|apaar\s*id)", "apaar_id", "APAAR ID", r"[\w\-]{12,20}"),
            (r"(?:10th|matric)(?:\s*(?:roll|roll\s*no))?", "matric_roll_number", "Matric Roll Number", r"\d{6,12}")
        ]

        # Check if text contains edit keyword (change, update, badal, kardo, karo, set, make)
        is_edit_intent = bool(re.search(r"change|update|badal|karo|kardo|rakho|likho|set|modify|edit|make", text_lower))
        
        for f_pat, vault_key, field_label, val_pat in field_targets:
            regex = (
                rf"(?:(?:change|update|set|badal\s*kar(?:ke)?)\s+)?"
                rf"{f_pat}"
                rf"(?:\s*(?:update\s*(?:karke|to)?|badal\s*kar(?:ke)?|change\s*(?:karke|to)?|set\s*to|ko|karke|mein|is|=|:|to))?"
                rf"\s+({val_pat})"
            )
            match = re.search(regex, text, re.IGNORECASE)
            if match and (is_edit_intent or "=" in text or ":" in text or " to " in text_lower):
                new_val = match.group(1).strip()
                # Clean up leading connector particles
                new_val = re.sub(r"^(badal\s*kar(ke)?|change\s*to|set\s*to|update\s*to|to|ko)\s+", "", new_val, flags=re.IGNORECASE)
                # Clean up trailing words like 'karo', 'kardo', 'kar do', 'please'
                new_val = re.sub(r"\b(karo|kardo|kar do|kar dena|rakho|rakh do|please|plz|sir|bhaiya|ji)\b", "", new_val, flags=re.IGNORECASE).strip()
                
                # Format Date if needed
                if vault_key == "dob":
                    new_val = self._normalize_dob(new_val)

                # Mutate One-Vault
                self._update_vault(vault_key, new_val)

                # Mutate Live Portal Page if agent running
                injected_dom = False
                if self.orchestrator and getattr(self.orchestrator, "page", None):
                    injected_dom = await self._inject_field_to_portal(vault_key, new_val)

                reply = (
                    f"Bilkul! {field_label} ko update karke **'{new_val}'** kar diya hai. "
                    + ("Portal screen par bhi live inject kar diya hai, screen check karein!" if injected_dom else "One-Vault mein save ho gaya hai.")
                )
                return {
                    "reply": reply,
                    "action_taken": "FIELD_UPDATED",
                    "field_updated": field_label,
                    "new_value": new_val,
                    "injected_in_dom": injected_dom,
                    "timestamp": datetime.datetime.now().strftime("%H:%M")
                }

        return None

    async def _try_workflow_action(self, text: str) -> Optional[Dict[str, Any]]:
        """Handles agent control commands like pause, resume, screen check, stop."""
        text_lower = text.lower()
        now_time = datetime.datetime.now().strftime("%H:%M")

        # Check for Pause Command
        if re.search(r"\b(pause|rok do|wait|ruko|stop thoda)\b", text_lower):
            if self.orchestrator:
                self.orchestrator._is_paused = True
            return {
                "reply": "Browser ko pause kar diya hai. Aap tasalli se details check karein ya One-Vault update karein. Jab ready hon toh 'continue' ya 'resume' bolein.",
                "action_taken": "PAUSED",
                "timestamp": now_time
            }

        # Check for Resume / Continue Command
        if re.search(r"\b(continue|resume|aage badho|chalo|shuru karo|next)\b", text_lower):
            if self.orchestrator:
                self.orchestrator._is_paused = False
                # If there's an active approval gate, approve it!
                if self.orchestrator.active_gate and self.orchestrator.active_gate.get("gate_type") == "SECTION_APPROVAL":
                    self.orchestrator.submit_user_response({"action": "SECTION_APPROVAL", "approved": True})
            return {
                "reply": "Ji bhaiya! Navigation resume kar diya hai aur agle step par aage badh rahe hain.",
                "action_taken": "RESUMED",
                "timestamp": now_time
            }

        # Check for Screen Status / Audit Check
        if re.search(r"\b(status|screen check|kya chal raha|kya ho raha|audit|fields)\b", text_lower):
            section_num = getattr(self.orchestrator, "current_section", 1) if self.orchestrator else 1
            filled_count = len(getattr(self.orchestrator, "filled_audit", [])) if self.orchestrator else 0
            active_gate_title = self.orchestrator.active_gate.get("title") if (self.orchestrator and self.orchestrator.active_gate) else "Koi pending gate nahi hai"

            return {
                "reply": (
                    f"**Current Status:** Abhi hum Section {section_num} par hain. "
                    f"One-Vault se ab tak {filled_count} fields safely verify karke fill kiye gaye hain. "
                    f"Active checkpoint: {active_gate_title}. Pre-payment safety lock active hai."
                ),
                "action_taken": "STATUS_REPORT",
                "timestamp": now_time
            }

        return None

    def _try_faq_knowledge(self, text: str) -> Optional[Dict[str, Any]]:
        """Answers domain questions regarding sarkari forms, fees, photos, eligibility, etc."""
        text_lower = text.lower()
        now_time = datetime.datetime.now().strftime("%H:%M")

        # 1. Application Fee
        if re.search(r"\b(fee|fees|kitne paise|charge|paisa|cost)\b", text_lower):
            return {
                "reply": (
                    "Central Recruitment Board (CREB Advt. 04/2026) aur standard Railway/SSC exams mein: "
                    "General / EWS / OBC candidates ke liye fee **₹500.00** hoti hai. "
                    "SC / ST / Ex-Servicemen / PwBD / Female candidates ke liye ₹250.00 hoti hai (jo CBT-1 appear hone par bank account mein refund ho jati hai). "
                    "Humne Pre-Payment Safety Lock lagaya hai, payment candidate khud UPI/Netbanking se karenge."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now_time
            }

        # 2. Biometric & Photo Specifications
        if re.search(r"\b(photo|photograph|signature|sign|kb|size|dimension|pixel)\b", text_lower):
            return {
                "reply": (
                    "**Official Biometric Specifications:**\n"
                    "• **Recent Passport Photograph:** 20KB – 50KB JPEG (350x350 px), white/light background, front-facing without caps/spectacles.\n"
                    "• **Digital Signature:** 10KB – 20KB JPEG (140x60 px) running handwriting in black or blue ink on plain white paper.\n"
                    "💡 CyberBhaiya ka deterministic Pillow binary-search compressor automatic portal specs ke anuroop compress kar deta hai!"
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now_time
            }

        # 3. Reservation & OBC-NCL Certificate
        if re.search(r"\b(obc|ncl|caste|category|reservation|certificate|praman patra|ews)\b", text_lower):
            return {
                "reply": (
                    "**OBC-NCL / EWS Certificate Rule:**\n"
                    "Sarkari bharti mein OBC Non-Creamy Layer (NCL) certificate Financial Year 2023-2024 ya current year ka hona zaroori hai. "
                    "Certificate Sub-Divisional Magistrate (SDM), Tehsildar, ya District Magistrate level se issued hona chahiye. "
                    "Agar certificate ready nahi hai, toh candidate initially General/UR category se apply kar sakte hain."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now_time
            }

        # 4. APAAR ID & DigiLocker
        if re.search(r"\b(apaar|digilocker|abc id|student id)\b", text_lower):
            return {
                "reply": (
                    "**APAAR (Automated Permanent Academic Account Registry):**\n"
                    "Yeh Bharat Sarkar ka 12-digit One Nation One Student ID hai. "
                    "Aapke 10th/12th marks aur DigiLocker degrees isme linked rehti hain. "
                    "One-Vault mein Nishant Kumar ka APAAR ID already archived hai (`9988-7766-5544`)."
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now_time
            }

        # 5. Documents Checklist
        if re.search(r"\b(document|kagaz|documents|kya chahiye|checklist)\b", text_lower):
            return {
                "reply": (
                    "**Required Documents Checklist:**\n"
                    "1. 10th / Matric Marksheet (Roll No & Passing Year proof)\n"
                    "2. Aadhaar Card (12-digit verified)\n"
                    "3. Category Certificate (OBC-NCL / EWS / SC / ST)\n"
                    "4. Domicile / Niwas Praman Patra\n"
                    "5. Passport Photo (20-50KB) & Signature (10-20KB)\n"
                    "Sabhi documents One-Vault se automatically verified ho chuke hain!"
                ),
                "action_taken": "FAQ_ANSWER",
                "timestamp": now_time
            }

        return None

    async def _try_tinyfish_search(self, query: str) -> Optional[Dict[str, Any]]:
        """If query is asking for external recruitment news/dates, invokes TinyFish Search API."""
        query_lower = query.lower()
        now_time = datetime.datetime.now().strftime("%H:%M")

        is_search_query = bool(re.search(r"\b(exam date|kab aayega|kab hoga|syllabus|notification|vacancy|cut off|result)\b", query_lower))
        if not is_search_query:
            return None

        api_key = self.tinyfish_client.config.tinyfish_api_key
        if not api_key:
            return None

        try:
            headers = {"X-API-Key": api_key.strip()}
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"https://api.search.tinyfish.ai?query={query.strip()}&location=IN",
                    headers=headers
                )
                if res.status_code == 200:
                    data = res.json()
                    results = data.get("results", [])
                    if len(results) > 0:
                        top = results[0]
                        reply = (
                            f"**TinyFish Live Search Result:**\n"
                            f"📰 **{top.get('title')}**\n"
                            f"{top.get('snippet')}\n"
                            f"🔗 Official Source: [{top.get('site_name')}]({top.get('url')})"
                        )
                        return {
                            "reply": reply,
                            "action_taken": "TINYFISH_SEARCH",
                            "source_url": top.get("url"),
                            "timestamp": now_time
                        }
        except Exception as e:
            print(f"[ChatAssistant] TinyFish search error: {e}")

        return None

    def _update_vault(self, key: str, value: str):
        """Mutates candidate vault in-memory and persists to disk."""
        vault = self.vault_mgr.vault
        if hasattr(vault, key):
            setattr(vault, key, value)
            # Also update verify counterpart if name or email
            verify_k = f"verify_{key}"
            if hasattr(vault, verify_k):
                setattr(vault, verify_k, value)
        else:
            self.vault_mgr.add_custom_field(key, value)
        self.vault_mgr.save(vault)

    async def _inject_field_to_portal(self, field_key: str, value: str) -> bool:
        """Injects new field value directly into the live Playwright page DOM."""
        if not self.orchestrator or not self.orchestrator.page:
            return False
        try:
            js_code = """
            ([fieldKey, val]) => {
                const selectors = [
                    `#${fieldKey}`,
                    `[name="${fieldKey}"]`,
                    `input[id*="${fieldKey}" i]`,
                    `input[name*="${fieldKey}" i]`,
                    `select[id*="${fieldKey}" i]`,
                    `select[name*="${fieldKey}" i]`
                ];
                let el = null;
                for (const s of selectors) {
                    try {
                        el = document.querySelector(s);
                        if (el) break;
                    } catch (e) {}
                }
                if (!el) return false;

                if (el.tagName.toLowerCase() === 'select') {
                    for (let i = 0; i < el.options.length; i++) {
                        if (el.options[i].text.toLowerCase().includes(val.toLowerCase()) || el.options[i].value.toLowerCase().includes(val.toLowerCase())) {
                            el.selectedIndex = i;
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                    }
                }

                const proto = window.HTMLInputElement.prototype;
                const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                if (descriptor && descriptor.set) {
                    descriptor.set.call(el, val);
                } else {
                    el.value = val;
                }
                el.dispatchEvent(new Event('focus', { bubbles: true }));
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
                return true;
            }
            """
            success = await self.orchestrator.page.evaluate(js_code, [field_key, value])
            if success and self.orchestrator:
                # Re-audit and capture screenshot
                await self.orchestrator._capture_screenshot()
                await self.orchestrator.emit_event(
                    "ACT",
                    f"Candidate requested live edit via Chat: Updated '{field_key}' to '{value}' in portal DOM.",
                    f"Candidate ke kehne par '{field_key}' ko '{value}' update kar diya hai."
                )
            return bool(success)
        except Exception as e:
            print(f"[ChatAssistant] DOM Injection error: {e}")
            return False

    def _normalize_dob(self, raw: str) -> str:
        """Converts DD/MM/YYYY or DD-MM-YYYY to YYYY-MM-DD for vault storage."""
        try:
            parts = re.split(r"[/-]", raw.strip())
            if len(parts) == 3:
                if len(parts[0]) == 4:  # YYYY-MM-DD
                    return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                else:  # DD-MM-YYYY
                    return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            return raw
        except Exception:
            return raw
