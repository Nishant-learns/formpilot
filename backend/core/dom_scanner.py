import re
from typing import Any, Dict, Optional, Tuple


class DOMScanner:
    """Reads a portal page and maps its fields to stable semantic keys."""

    DETECTION_JS = r"""
    () => {
        const frameworks = [];
        if (window.__reactFiber || document.querySelector('[data-reactroot]') || window._reactRootContainer) frameworks.push('React');
        if (window.ng || document.querySelector('[ng-version]') || document.querySelector('[ng-app]')) frameworks.push('Angular');
        if (window.__vue__ || window.__vue_app__ || document.querySelector('[data-v-]')) frameworks.push('Vue');
        if (window.Sys && window.Sys.WebForms) frameworks.push('ASP.NET Ajax');
        if (document.getElementById('__VIEWSTATE')) frameworks.push('ASP.NET WebForms');
        if (window.Ext) frameworks.push('ExtJS');
        if (window.jQuery) frameworks.push('jQuery');
        if (frameworks.length === 0) frameworks.push('Standard HTML5');

        const isVisible = (el) => {
            if (!el) return false;
            if (el.checkVisibility) {
                try { return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }); } catch (e) {}
            }
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
        };

        const getLabel = (el) => {
            let labelText = '';
            if (el.id) {
                const labelEl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                if (labelEl) labelText += ' ' + labelEl.innerText;
            }
            const parentLabel = el.closest('label');
            if (parentLabel) labelText += ' ' + parentLabel.innerText;
            if (el.getAttribute('aria-label')) labelText += ' ' + el.getAttribute('aria-label');
            if (el.getAttribute('aria-labelledby')) {
                const ariaEl = document.getElementById(el.getAttribute('aria-labelledby'));
                if (ariaEl) labelText += ' ' + ariaEl.innerText;
            }
            if (el.placeholder) labelText += ' ' + el.placeholder;
            if (el.title) labelText += ' ' + el.title;
            if (el.name) labelText += ' ' + el.name;
            const td = el.closest('td');
            if (td && td.previousElementSibling) labelText += ' ' + td.previousElementSibling.innerText;
            return labelText.replace(/\s+/g, ' ').trim();
        };

        const clickables = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"], .btn, .loginButton'));
        const gateways = [];
        for (const btn of clickables) {
            if (!isVisible(btn)) continue;
            const text = (btn.innerText || btn.value || btn.getAttribute('aria-label') || '').trim();
            const lower = text.toLowerCase();
            let gType = null;
            if (/new\s*registration|create\s*account|register\s*here|new\s*user|otr|apply\s*online|sign\s*up/i.test(lower)) {
                gType = 'NEW_REGISTRATION';
            } else if (/candidate\s*login|sign\s*in|login|log\s*in|already\s*registered/i.test(lower)) {
                gType = 'LOGIN';
            } else if (/aadhaar|digilocker/i.test(lower)) {
                gType = 'DIGILOCKER_AADHAAR';
            }
            if (gType) {
                const rect = btn.getBoundingClientRect();
                gateways.push({
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

        const inputs = [];
        const rawInputs = Array.from(document.querySelectorAll('input, select, textarea, [contenteditable="true"]'));
        let index = 0;
        for (const el of rawInputs) {
            if (el.type === 'hidden') continue;
            if (!isVisible(el)) continue;
            const rect = el.getBoundingClientRect();
            const tag = el.tagName.toLowerCase();
            const type = (el.type || (tag === 'select' ? 'select' : 'text')).toLowerCase();
            let options = [];
            if (tag === 'select') {
                options = Array.from(el.options).map(o => ({ text: o.text.trim(), value: o.value })).filter(o => o.text && o.value);
            }
            inputs.push({
                index: index++,
                tagName: tag,
                type: type,
                id: el.id || '',
                name: el.name || '',
                label: getLabel(el),
                value: el.value || el.innerText || '',
                checked: el.checked || false,
                required: el.required || el.getAttribute('aria-required') === 'true' || getLabel(el).includes('*'),
                placeholder: el.placeholder || '',
                options: options,
                rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
            });
        }

        const nextButtons = [];
        for (const btn of clickables) {
            if (!isVisible(btn)) continue;
            const text = (btn.innerText || btn.value || '').trim();
            if (/save\s*&\s*next|save\s*and\s*next|proceed|continue|next\s*step|submit|log\s*in|sign\s*in/i.test(text)) {
                const rect = btn.getBoundingClientRect();
                nextButtons.push({
                    text: text,
                    id: btn.id || null,
                    name: btn.name || null,
                    className: btn.className || '',
                    rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
                });
            }
        }

        const captchaElements = [];
        const captchaCandidates = Array.from(document.querySelectorAll('img, canvas, [id*="captcha" i], [class*="captcha" i]'));
        for (const el of captchaCandidates) {
            if (!isVisible(el)) continue;
            const idLower = (el.id || '').toLowerCase();
            const classLower = String(el.className || '').toLowerCase();
            const src = el.src || '';
            const tagName = el.tagName.toLowerCase();
            if (!['canvas', 'img'].includes(tagName)) continue;
            if (idLower.includes('captcha') || classLower.includes('captcha') || src.includes('captcha') || tagName === 'canvas') {
                const rect = el.getBoundingClientRect();
                if (rect.width > 40 && rect.height > 15) {
                    captchaElements.push({
                        tagName: tagName,
                        id: el.id || null,
                        rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
                    });
                }
            }
        }

        const errors = [];
        const errorNodes = Array.from(document.querySelectorAll('.error, .alert-danger, .text-danger, .invalid-feedback, [role="alert"], .mat-error, .field-validation-error, span[style*="red"], font[color="red"]'));
        for (const node of errorNodes) {
            if (!isVisible(node)) continue;
            const txt = (node.innerText || '').trim();
            if (txt && !txt.includes('* indicates') && !txt.includes('Password must') && txt.length > 3) errors.push(txt);
        }

        const bodyText = (document.body && document.body.innerText ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
        const lowerBody = bodyText.toLowerCase();
        const paymentWords = ['application fee', 'pay fee', 'payment', 'checkout', 'net banking', 'debit card', 'credit card', 'upi', 'proceed to pay'];
        const paymentSignals = paymentWords.filter(w => lowerBody.includes(w)).length;
        const activeSection = document.querySelector('.form-section.active, .section.active, [data-section].active');
        const heading = document.querySelector('.form-section.active h2, .section.active h2, h1, h2');
        const paymentButton = Array.from(document.querySelectorAll('button, input[type="submit"], a[role="button"]'))
            .filter(isVisible)
            .find(b => {
                const text = (b.innerText || b.value || '').trim();
                const isPayment = /\b(pay|payment|checkout)\b/i.test(text);
                const isReview = /pre[-\s]*payment|review|back|previous/i.test(text);
                return isPayment && !isReview;
            });
        return {
            title: document.title,
            url: window.location.href,
            frameworks: frameworks,
            gateways: gateways,
            inputs: inputs,
            nextButtons: nextButtons,
            captchaElements: captchaElements,
            errors: errors,
            visibleText: bodyText.slice(0, 4000),
            paymentSignals: paymentSignals,
            hasPaymentButton: !!paymentButton,
            activeSectionId: activeSection ? (activeSection.id || '') : '',
            stepHeading: heading ? (heading.innerText || '').trim().slice(0, 160) : '',
            formCount: document.querySelectorAll('form').length
        };
    }
    """

    EXTRACT_VALUES_JS = r"""
    (includeHidden = false) => {
        const isVisible = (el) => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
        };
        const getLabel = (el) => {
            let text = '';
            if (el.id) {
                const labelEl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                if (labelEl) text += ' ' + labelEl.innerText;
            }
            const parent = el.closest('label');
            if (parent) text += ' ' + parent.innerText;
            if (el.getAttribute('aria-label')) text += ' ' + el.getAttribute('aria-label');
            if (el.name) text += ' ' + el.name;
            return text.replace(/\s+/g, ' ').trim();
        };
        return Array.from(document.querySelectorAll('input, select, textarea, [contenteditable="true"]'))
            .filter(el => el.type !== 'hidden' && (includeHidden || isVisible(el)))
            .map((el, index) => ({
                index: index,
                id: el.id || '',
                name: el.name || '',
                label: getLabel(el),
                type: (el.type || el.tagName.toLowerCase()).toLowerCase(),
                value: el.type === 'file' ? (el.files && el.files.length ? el.files[0].name : '') : (el.value || el.innerText || ''),
                checked: !!el.checked,
                selectedText: el.tagName && el.tagName.toLowerCase() === 'select' && el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : ''
            }));
    }
    """

    @classmethod
    def classify_field(cls, field_meta: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """Map a portal input to a semantic key and a verify/confirm flag."""
        combined = " ".join(
            str(field_meta.get(k, "") or "")
            for k in ("id", "name", "label", "placeholder", "aria_label")
        ).lower()
        field_type = str(field_meta.get("type", "") or "").lower()
        is_verify = bool(re.search(r"\bconfirm|verify|re-?enter|repeat", combined))

        # Never fill one-time codes or CAPTCHA answers from the vault.  They
        # are handled by an explicit user checkpoint.
        if re.search(r"otp|one[-\s]?time\s*(password|code)|verification\s*code|auth(entication)?\s*code", combined):
            return (None, False)
        if re.search(r"captcha|security\s*check|enter\s*(the\s*)?code\s*(shown|above)", combined):
            return (None, False)

        # Identity
        if re.search(r"father|guardian", combined):
            return ("verify_father_name" if is_verify else "father_name", is_verify)
        if re.search(r"mother", combined):
            return ("verify_mother_name" if is_verify else "mother_name", is_verify)
        if re.search(r"candidate\s*name|applicant\s*name|full\s*name|student\s*name|your\s*name", combined) or (
            re.search(r"\bname\b", combined) and not re.search(r"board|school|college|user|father|mother|guardian", combined)
        ):
            return ("verify_full_name" if is_verify else "full_name", is_verify)

        if re.search(r"\bdob\b|birth|date_of_birth|dateofbirth", combined):
            return ("dob", is_verify)
        if re.search(r"gender|\bsex\b", combined):
            return ("gender", is_verify)
        if re.search(r"marital", combined):
            return ("marital_status", is_verify)
        if re.search(r"religion", combined):
            return ("religion", is_verify)
        if re.search(r"nationality", combined):
            return ("nationality", is_verify)

        # Reservation / domicile
        if re.search(r"sub[-\s]?caste|subcaste", combined):
            return ("sub_caste", is_verify)
        if re.search(r"category|caste|community|social_status", combined):
            return ("category", is_verify)
        if re.search(r"domicile|state_of_origin|residential_state", combined):
            return ("domicile_state", is_verify)
        if re.search(r"disab|differently\s*abled|pwd", combined):
            return ("is_differently_abled", is_verify)
        if re.search(r"ex[-\s]?serviceman", combined):
            return ("is_ex_serviceman", is_verify)

        # Contact (after OTP/CAPTCHA guards)
        if re.search(r"mobile|phone|contact_no|cell|whatsapp", combined):
            return ("mobile", is_verify)
        if re.search(r"alternate.*(mobile|phone)|secondary.*(mobile|phone)", combined):
            return ("alternate_mobile", is_verify)
        if re.search(r"email|mail_id|e-mail", combined):
            return ("confirm_email" if is_verify else "email", is_verify)

        # Identifiers
        if re.search(r"aadhaar|aadhar|uidai", combined):
            return ("aadhaar_number", is_verify)
        if re.search(r"apaar", combined):
            return ("apaar_id", is_verify)
        if re.search(r"digilocker", combined):
            return ("digilocker_id", is_verify)
        if re.search(r"height", combined):
            return ("height_cm", is_verify)
        if re.search(r"chest", combined):
            return ("chest_cm", is_verify)
        if re.search(r"reg_id|registration\s*(id|no|number)|reg_no|otr|application\s*(id|no|number)", combined):
            return ("registration_id", is_verify)
        if re.search(r"password|pwd|passcode", combined):
            return ("account_password", is_verify)

        # Address
        if re.search(r"pincode|pin_code|postal_code|zip", combined):
            return ("pincode", is_verify)
        if re.search(r"present.*(district)|correspondence.*district", combined):
            return ("present_district", is_verify)
        if re.search(r"present.*(state)|correspondence.*state", combined):
            return ("present_state", is_verify)
        if re.search(r"present.*(address|addr)|correspondence.*(address|addr)", combined):
            return ("present_address_line_1", is_verify)
        if re.search(r"village|town|city", combined):
            return ("village_town_city", is_verify)
        if re.search(r"district", combined):
            return ("district", is_verify)
        if re.search(r"\bstate\b", combined) and not re.search(r"statement|domicile", combined):
            return ("state", is_verify)
        if re.search(r"address\s*(line)?\s*2|landmark|locality", combined):
            return ("address_line_2", is_verify)
        if re.search(r"address|permanent_address", combined):
            return ("address_line_1", is_verify)

        # Identification marks
        if re.search(r"mark\s*2", combined):
            return ("identification_mark_2", is_verify)
        if re.search(r"mark\s*1|identification_mark|mole|scar", combined):
            return ("identification_mark_1", is_verify)

        # File uploads (before academic text fields)
        if field_type == "file":
            if re.search(r"photo|photograph|pic|image", combined):
                return ("photo_upload", is_verify)
            if re.search(r"sign|signature|\bsig\b|sig_", combined):
                return ("signature_upload", is_verify)
            if re.search(r"10th|matric|marksheet", combined):
                return ("matric_cert_upload", is_verify)
            return (None, False)

        # Intermediate / 12th (must be checked before matric)
        if re.search(r"intermediate|12th|senior\s*secondary|higher\s*secondary|plus\s*two|\bpuc\b", combined):
            if re.search(r"roll|seat", combined):
                return ("intermediate_roll_number", is_verify)
            if re.search(r"board", combined):
                return ("intermediate_board", is_verify)
            if re.search(r"stream|subject|faculty", combined):
                return ("intermediate_stream", is_verify)
            if re.search(r"year|passing", combined):
                return ("intermediate_passing_year", is_verify)
            if re.search(r"cgpa|gpa", combined):
                return ("intermediate_percentage", is_verify)
            if re.search(r"total\s*marks", combined):
                return ("intermediate_total_marks", is_verify)
            if re.search(r"obtained|marks|percentage", combined):
                return ("intermediate_percentage", is_verify)
            if re.search(r"college|school", combined):
                return ("intermediate_college_name", is_verify)
            if re.search(r"certificate", combined):
                return ("intermediate_certificate_number", is_verify)

        # Graduation
        if re.search(r"\b(graduat\w*|bachelor\w*|b\.?\s*(sc|com|a|tech|e)|degree|university)\b", combined):
            if re.search(r"roll|enrol", combined):
                return ("graduation_roll_number", is_verify)
            if re.search(r"university|college|institute", combined):
                return ("graduation_university", is_verify)
            if re.search(r"year|passing", combined):
                return ("graduation_passing_year", is_verify)
            if re.search(r"cgpa|gpa|percentage|marks", combined):
                return ("graduation_percentage", is_verify)
            if re.search(r"degree|course|stream", combined):
                return ("graduation_degree_name", is_verify)

        # Matric / 10th
        if re.search(r"10th|matric|high\s*school|secondary\s*school", combined):
            if re.search(r"roll|seat", combined):
                return ("matric_roll_number", is_verify)
            if re.search(r"board", combined):
                return ("matric_board", is_verify)
            if re.search(r"year|passing", combined):
                return ("matric_passing_year", is_verify)
            if re.search(r"cgpa|gpa", combined):
                return ("matric_cgpa", is_verify)
            if re.search(r"total\s*marks", combined):
                return ("matric_total_marks", is_verify)
            if re.search(r"obtained|marks|percentage", combined):
                return ("matric_percentage", is_verify)
            if re.search(r"school", combined):
                return ("matric_school_name", is_verify)
            if re.search(r"certificate", combined):
                return ("matric_certificate_number", is_verify)

        # Generic custom fields that portals sometimes add.
        if re.search(r"mother\s*tongue|language", combined):
            return ("mother_tongue", is_verify)
        if re.search(r"employment|occupation", combined):
            return ("employment_status", is_verify)
        if re.search(r"criminal", combined):
            return ("criminal_case_pending", is_verify)
        if re.search(r"debarred", combined):
            return ("debarred_from_exam", is_verify)

        return (None, False)

    INJECTION_JS = r"""
    ([targetMeta, value]) => {
        let el = null;
        if (targetMeta.id) el = document.getElementById(targetMeta.id);
        if (!el && targetMeta.name) {
            el = document.querySelector(`[name="${CSS.escape(targetMeta.name)}"]`);
        }
        if (!el && targetMeta.index !== undefined) {
            const raw = Array.from(document.querySelectorAll('input, select, textarea, [contenteditable="true"]')).filter(e => {
                if (e.type === 'hidden') return false;
                const rect = e.getBoundingClientRect();
                const style = window.getComputedStyle(e);
                return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            });
            el = raw[targetMeta.index];
        }
        if (!el) return { success: false, reason: 'Field not found on the page' };
        if (el.type === 'file') return { success: false, reason: 'File fields need a separate upload step' };

        const norm = (v) => String(v == null ? '' : v).toLowerCase().replace(/[^a-z0-9]/g, '');
        const targetRaw = String(value == null ? '' : value).trim();
        const target = norm(targetRaw);

        const selectLabel = (node) => {
            if (!node) return '';
            let text = '';
            if (node.id) {
                const l = document.querySelector(`label[for="${CSS.escape(node.id)}"]`);
                if (l) text += ' ' + l.innerText;
            }
            const p = node.closest('label');
            if (p) text += ' ' + p.innerText;
            return text.replace(/\s+/g, ' ').trim();
        };

        if (el.tagName.toLowerCase() === 'select') {
            const options = Array.from(el.options);
            let match = options.find(o => norm(o.value) === target || norm(o.text) === target);
            if (!match) match = options.find(o => norm(o.text).includes(target) || target.includes(norm(o.text)));
            if (!match && target === 'obcncl') {
                match = options.find(o => norm(o.text).includes('obc') && norm(o.text).includes('ncl'));
            }
            if (!match && ['ur', 'general', 'unreserved'].includes(target)) {
                match = options.find(o => norm(o.text).includes('general') || norm(o.text).includes('unreserved') || norm(o.text) === 'ur');
            }
            if (!match && ['yes', 'no'].includes(target)) {
                match = options.find(o => norm(o.text) === target);
            }
            if (!match) return { success: false, reason: 'No matching option', options: options.map(o => o.text) };
            el.value = match.value;
            el.selectedIndex = match.index;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return { success: true, method: 'select', value: match.value, text: match.text };
        }

        if (el.type === 'radio') {
            const group = el.name
                ? Array.from(document.querySelectorAll(`input[type="radio"][name="${CSS.escape(el.name)}"]`))
                : [el];
            let match = group.find(r => norm(r.value) === target);
            if (!match) match = group.find(r => norm(selectLabel(r)).includes(target));
            if (!match && ['yes', 'no'].includes(target)) {
                match = group.find(r => norm(r.value) === target || norm(selectLabel(r)) === target);
            }
            if (!match) return { success: false, reason: 'No matching radio option' };
            match.checked = true;
            match.dispatchEvent(new Event('input', { bubbles: true }));
            match.dispatchEvent(new Event('change', { bubbles: true }));
            return { success: true, method: 'radio', value: match.value };
        }

        if (el.type === 'checkbox') {
            const wantsNo = ['no', 'false', '0', 'unchecked'].includes(target);
            el.checked = !wantsNo;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return { success: true, method: 'checkbox', value: el.checked };
        }

        let finalValue = targetRaw;
        if (el.type === 'date') {
            const dmy = targetRaw.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})$/);
            if (dmy) finalValue = `${dmy[3]}-${dmy[2].padStart(2, '0')}-${dmy[1].padStart(2, '0')}`;
        }

        el.focus();
        if (el.isContentEditable) {
            el.innerText = finalValue;
        } else {
            const proto = window.HTMLInputElement.prototype;
            const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
            if (descriptor && descriptor.set) descriptor.set.call(el, finalValue);
            else el.value = finalValue;
        }
        try {
            el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: finalValue }));
        } catch (e) {
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        return { success: true, method: el.type === 'date' ? 'date' : 'input', value: finalValue };
    }
    """
