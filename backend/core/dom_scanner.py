import re
from typing import Dict, Any, List, Optional, Tuple

class DOMScanner:
    """Universal Deep Landscape DOM Scanner & Semantic Mapper."""

    DETECTION_JS = """
    () => {
        // Framework Sensing
        const frameworks = [];
        if (window.__reactFiber || document.querySelector('[data-reactroot]') || window._reactRootContainer) frameworks.push('React');
        if (window.ng || document.querySelector('[ng-version]') || document.querySelector('[ng-app]')) frameworks.push('Angular');
        if (window.__vue__ || window.__vue_app__ || document.querySelector('[data-v-]')) frameworks.push('Vue');
        if (window.Sys && window.Sys.WebForms) frameworks.push('ASP.NET Ajax');
        if (document.getElementById('__VIEWSTATE')) frameworks.push('ASP.NET WebForms');
        if (window.Ext) frameworks.push('ExtJS');
        if (window.jQuery) frameworks.push('jQuery');
        if (frameworks.length === 0) frameworks.push('Standard HTML5');

        // Helper: universal visibility
        const isVisible = (el) => {
            if (!el) return false;
            if (el.checkVisibility) {
                return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
            }
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
        };

        // Extract label for an element
        const getLabel = (el) => {
            let labelText = '';
            // 1. Associated label via 'for'
            if (el.id) {
                const labelEl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                if (labelEl) labelText += ' ' + labelEl.innerText;
            }
            // 2. Parent label
            const parentLabel = el.closest('label');
            if (parentLabel) labelText += ' ' + parentLabel.innerText;
            // 3. Aria attributes
            if (el.getAttribute('aria-label')) labelText += ' ' + el.getAttribute('aria-label');
            if (el.getAttribute('aria-labelledby')) {
                const ariaEl = document.getElementById(el.getAttribute('aria-labelledby'));
                if (ariaEl) labelText += ' ' + ariaEl.innerText;
            }
            // 4. Placeholder, title, name
            if (el.placeholder) labelText += ' ' + el.placeholder;
            if (el.title) labelText += ' ' + el.title;
            if (el.name) labelText += ' ' + el.name;
            // 5. Surrounding table cell header or preceding sibling
            const td = el.closest('td');
            if (td && td.previousElementSibling) {
                labelText += ' ' + td.previousElementSibling.innerText;
            }
            return labelText.replace(/\\s+/g, ' ').trim();
        };

        // Scan Gateway Entry Points (New Registration vs Login)
        const gatewayButtons = [];
        const candidateClickables = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"], .btn, .loginButton'));
        for (const btn of candidateClickables) {
            if (!isVisible(btn)) continue;
            const text = (btn.innerText || btn.value || btn.getAttribute('aria-label') || '').trim();
            const lower = text.toLowerCase();
            let gType = null;
            if (/new\\s*registration|create\\s*account|register\\s*here|new\\s*user|otr|apply\\s*online|sign\\s*up/i.test(lower)) {
                gType = 'NEW_REGISTRATION';
            } else if (/candidate\\s*login|sign\\s*in|login|log\\s*in|already\\s*registered/i.test(lower)) {
                gType = 'LOGIN';
            } else if (/aadhaar|digilocker/i.test(lower)) {
                gType = 'DIGILOCKER_AADHAAR';
            }
            if (gType) {
                const rect = btn.getBoundingClientRect();
                gatewayButtons.push({
                    text: text,
                    type: gType,
                    tagName: btn.tagName.toLowerCase(),
                    id: btn.id || null,
                    name: btn.name || null,
                    className: btn.className || '',
                    rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
                });
            }
        }

        // Scan Form Interactive Inputs
        const inputs = [];
        const rawInputs = Array.from(document.querySelectorAll('input, select, textarea'));
        let index = 0;
        for (const el of rawInputs) {
            if (el.type === 'hidden') continue;
            const visible = isVisible(el);
            if (!visible) continue;

            const rect = el.getBoundingClientRect();
            const label = getLabel(el);
            const tag = el.tagName.toLowerCase();
            const type = (el.type || 'text').toLowerCase();

            let options = [];
            if (tag === 'select') {
                options = Array.from(el.options).map(o => ({
                    text: o.text.trim(),
                    value: o.value
                })).filter(o => o.text && o.value);
            }

            inputs.push({
                index: index++,
                tagName: tag,
                type: type,
                id: el.id || '',
                name: el.name || '',
                label: label,
                value: el.value || '',
                checked: el.checked || false,
                required: el.required || el.getAttribute('aria-required') === 'true' || label.includes('*'),
                placeholder: el.placeholder || '',
                options: options,
                rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
            });
        }

        // Scan Section Containers & Save/Next triggers
        const nextButtons = [];
        for (const btn of candidateClickables) {
            if (!isVisible(btn)) continue;
            const text = (btn.innerText || btn.value || '').trim();
            if (/save\\s*&\\s*next|save\\s*and\\s*next|proceed|continue|next\\s*step|submit/i.test(text)) {
                const rect = btn.getBoundingClientRect();
                nextButtons.push({
                    text: text,
                    id: btn.id || null,
                    rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
                });
            }
        }

        // Detect Visual CAPTCHA Elements
        const captchaElements = [];
        const captchaCandidates = Array.from(document.querySelectorAll('img, canvas, [id*="captcha" i], [class*="captcha" i]'));
        for (const el of captchaCandidates) {
            if (!isVisible(el)) continue;
            const idLower = (el.id || '').toLowerCase();
            const classLower = (el.className || '').toLowerCase();
            const src = el.src || '';
            if (idLower.includes('captcha') || classLower.includes('captcha') || src.includes('captcha') || el.tagName.toLowerCase() === 'canvas') {
                const rect = el.getBoundingClientRect();
                if (rect.width > 40 && rect.height > 15) {
                    captchaElements.push({
                        tagName: el.tagName.toLowerCase(),
                        id: el.id || null,
                        rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
                    });
                }
            }
        }

        // Scan Validation Errors
        const errors = [];
        const errorNodes = Array.from(document.querySelectorAll('.error, .alert-danger, .text-danger, .invalid-feedback, [role="alert"], .mat-error, .field-validation-error, span[style*="red"], font[color="red"]'));
        for (const node of errorNodes) {
            if (!isVisible(node)) continue;
            const txt = (node.innerText || '').trim();
            // Filter out non-error instructions
            if (txt && !txt.includes('* indicates') && !txt.includes('Password must') && txt.length > 3) {
                errors.push(txt);
            }
        }

        return {
            title: document.title,
            url: window.location.href,
            frameworks: frameworks,
            gateways: gatewayButtons,
            inputs: inputs,
            nextButtons: nextButtons,
            captchaElements: captchaElements,
            errors: errors
        };
    }
    """

    @classmethod
    def classify_field(cls, field_meta: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """
        Maps a DOM input element to a candidate semantic field key.
        Returns: (semantic_key, is_verify_confirm_field)
        """
        combined = f"{field_meta.get('id', '')} {field_meta.get('name', '')} {field_meta.get('label', '')} {field_meta.get('placeholder', '')}".lower()
        
        # Check if confirmation / verify field
        is_verify = bool(re.search(r"confirm|verify|re-enter|reenter|re_enter|reenter", combined))

        # Check Names
        if re.search(r"father|guardian", combined):
            return ("verify_father_name" if is_verify else "father_name", is_verify)
        if re.search(r"mother", combined):
            return ("verify_mother_name" if is_verify else "mother_name", is_verify)
        if re.search(r"candidate\s*name|applicant\s*name|full\s*name|student\s*name|your\s*name", combined) or (re.search(r"\bname\b", combined) and not re.search(r"board|school|college|user", combined)):
            return ("verify_full_name" if is_verify else "full_name", is_verify)

        # Date of Birth
        if re.search(r"dob|birth|date_of_birth|dateofbirth", combined):
            return ("dob", is_verify)

        # Gender
        if re.search(r"gender|sex", combined):
            return ("gender", is_verify)

        # Mobile
        if re.search(r"mobile|phone|contact_no|cell", combined):
            return ("mobile", is_verify)

        # Email
        if re.search(r"email|mail_id|e-mail", combined):
            return ("confirm_email" if is_verify else "email", is_verify)

        # Aadhaar
        if re.search(r"aadhaar|aadhar|uidai", combined):
            return ("aadhaar_number", is_verify)

        # Category / Caste
        if re.search(r"category|caste|community|social_status", combined):
            return ("category", is_verify)

        # Domicile
        if re.search(r"domicile|state_of_origin|residential_state", combined):
            return ("domicile_state", is_verify)

        # Address & Pin
        if re.search(r"pincode|pin_code|postal_code|zip", combined):
            return ("pincode", is_verify)
        if re.search(r"district", combined):
            return ("district", is_verify)
        if re.search(r"state", combined) and not re.search(r"statement|domicile", combined):
            return ("state", is_verify)
        if re.search(r"address|permanet_address|vill", combined):
            return ("address_line_1", is_verify)

        # Identification marks
        if re.search(r"mark\s*1|identification_mark|mole|scar", combined):
            return ("identification_mark_1", is_verify)
        if re.search(r"mark\s*2", combined):
            return ("identification_mark_2", is_verify)

        # Academics (10th / Matric)
        if re.search(r"10th|matric|high\s*school", combined):
            if re.search(r"roll", combined):
                return ("matric_roll_number", is_verify)
            if re.search(r"board", combined):
                return ("matric_board", is_verify)
            if re.search(r"year|passing", combined):
                return ("matric_passing_year", is_verify)
            if re.search(r"mark|percentage|cgpa", combined):
                return ("matric_percentage", is_verify)
            if re.search(r"school", combined):
                return ("matric_school_name", is_verify)

        # File Uploads
        if field_meta.get("type") == "file":
            if re.search(r"photo|photograph|pic|image", combined):
                return ("photo_upload", is_verify)
            if re.search(r"sign|signature", combined):
                return ("signature_upload", is_verify)
            if re.search(r"10th|matric|marksheet", combined):
                return ("matric_cert_upload", is_verify)

        # Custom fields check (APAAR, DigiLocker, Height, etc.)
        if re.search(r"apaar", combined):
            return ("apaar_id", is_verify)
        if re.search(r"digilocker", combined):
            return ("digilocker_id", is_verify)
        if re.search(r"height", combined):
            return ("height_cm", is_verify)
        if re.search(r"chest", combined):
            return ("chest_cm", is_verify)

        # Registration / OTR ID / Login credentials
        if re.search(r"reg_id|registration_id|registration_no|reg_no|otr_id|application_no", combined):
            return ("registration_id", is_verify)
        if re.search(r"password|pwd|passcode", combined):
            return ("account_password", is_verify)

        # Unknown or unmapped
        return (None, False)

    INJECTION_JS = """
    (targetMeta, value) => {
        let el = null;
        if (targetMeta.id) {
            el = document.getElementById(targetMeta.id);
        }
        if (!el && targetMeta.name) {
            el = document.querySelector(`[name="${CSS.escape(targetMeta.name)}"]`);
        }
        if (!el && targetMeta.index !== undefined) {
            const raw = Array.from(document.querySelectorAll('input, select, textarea')).filter(e => {
                if (e.type === 'hidden') return false;
                const rect = e.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            });
            el = raw[targetMeta.index];
        }
        if (!el) return { success: false, reason: 'Element not found in live DOM' };

        // Handle Select dropdown
        if (el.tagName.toLowerCase() === 'select') {
            let foundVal = null;
            const target = String(value).toLowerCase().trim();
            for (let i = 0; i < el.options.length; i++) {
                const optText = el.options[i].text.toLowerCase().trim();
                const optVal = el.options[i].value.toLowerCase().trim();
                if (optText === target || optVal === target || optText.includes(target) || target.includes(optText)) {
                    foundVal = el.options[i].value;
                    el.selectedIndex = i;
                    break;
                }
            }
            if (foundVal !== null) {
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return { success: true, method: 'select', value: foundVal };
            }
            return { success: false, reason: 'Option not matched in select dropdown' };
        }

        // Handle Radio & Checkbox
        if (el.type === 'radio' || el.type === 'checkbox') {
            el.checked = true;
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return { success: true, method: 'check' };
        }

        // Handle Text, Password, Email, Tel, Number Inputs with React/Angular synthetic setter
        const proto = window.HTMLInputElement.prototype;
        const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
        if (descriptor && descriptor.set) {
            descriptor.set.call(el, value);
        } else {
            el.value = value;
        }

        // Dispatch full synthetic event lifecycle
        el.dispatchEvent(new Event('focus', { bubbles: true }));
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));

        return { success: true, method: 'input_setter', value: value };
    }
    """
