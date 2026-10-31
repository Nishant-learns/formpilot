"""Portal-specific hints on top of the universal DOM scanner.

The orchestrator works on any HTML form.  Adapters only answer a few
questions that are expensive or ambiguous to infer from raw DOM: what step is
this, is this the payment page, and which button advances the flow.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from playwright.async_api import Page


_ENTRY_HREF_RE = re.compile(
    r"(?:^|/)(?:login|log-in|signin|sign-in|signup|sign-up|register|registration|"
    r"create-account|new-registration)(?:/|$|[?#])",
    re.IGNORECASE,
)
_BACK_RE = re.compile(r"\b(?:back|previous|cancel)\b", re.IGNORECASE)
_NAV_PRIORITY_RE = re.compile(
    r"save\s*&\s*next|save\s*and\s*next|next\s*step|\bnext\b|continue|proceed",
    re.IGNORECASE,
)
_ACTION_PRIORITY_RE = re.compile(
    r"verify|confirm|send\s*otp|get\s*otp|create\s*(?:an?\s*)?account|"
    r"account\s*creation|register|log\s*in|sign\s*in|apply|save|update",
    re.IGNORECASE,
)
_FINAL_PRIORITY_RE = re.compile(
    r"\b(?:submit|pay|payment|checkout|finish|complete\s+(?:application|registration))\b",
    re.IGNORECASE,
)


class BasePortalAdapter:
    name = "generic"
    payment_label = "payment"

    def current_step(self, page: Page, dom: dict[str, Any]) -> int:
        active = str(dom.get("activeSectionId") or "")
        if active.startswith("sec-"):
            try:
                return int(active.split("-", 1)[1])
            except ValueError:
                pass
        return 1

    def step_key(self, page: Page, dom: dict[str, Any]) -> str:
        active = str(dom.get("activeSectionId") or "")
        if active:
            return active
        return f"{dom.get('url', '')}|{dom.get('stepHeading', '')}"

    def is_payment_page(self, page: Page, dom: dict[str, Any]) -> bool:
        if dom.get("hasPaymentButton"):
            return True
        url = str(dom.get("url") or "").lower()
        if any(token in url for token in ("/payment", "/checkout", "/pay-fee")):
            return True
        text = str(dom.get("visibleText") or "").lower()
        return "application fee" in text and ("proceed to pay" in text or "payment gateway" in text)

    async def _page_identity(self, page: Page) -> dict[str, Any]:
        try:
            return await page.evaluate(
                """() => {
                    const section = document.querySelector(
                        '.form-section.active, .section.active, [data-section].active'
                    );
                    const heading = document.querySelector(
                        '.form-section.active h2, .section.active h2, h1, h2'
                    );
                    return {
                        url: location.href,
                        section: section ? (section.id || '') : '',
                        heading: heading ? (heading.innerText || '').trim().slice(0, 160) : '',
                    };
                }"""
            )
        except Exception:
            return {"url": getattr(page, "url", ""), "section": "", "heading": ""}

    async def wait_for_step_change(
        self,
        page: Page,
        previous_step: int,
        *,
        timeout_ms: int = 12000,
        before: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Return True only when the page actually changed.

        The old implementation always returned True, which let the UI claim a
        section was saved even when the click did nothing.  A change means a
        different URL, active section, or heading.
        """
        baseline = before or await self._page_identity(page)
        try:
            await page.wait_for_timeout(350)
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass
        after = await self._page_identity(page)
        return any(
            str(baseline.get(key) or "") != str(after.get(key) or "")
            for key in ("url", "section", "heading")
        )

    def next_candidates(self, dom: dict[str, Any]) -> List[dict[str, Any]]:
        """Return navigation candidates ordered by explicit action priority.

        The adapter never returns ``.first``.  ``find_next_button`` only accepts
        a unique best candidate; if two different controls are equally likely,
        the orchestrator must ask the human instead of guessing.
        """
        candidates: List[dict[str, Any]] = []
        for button in dom.get("nextButtons") or []:
            text = str(button.get("text") or "").strip()
            if not text or _BACK_RE.search(text):
                continue
            if button.get("visible") is False or button.get("interactable") is False:
                continue
            if button.get("covered_by") or button.get("coveredBy"):
                continue
            href = str(button.get("href") or "")
            if href and _ENTRY_HREF_RE.search(href):
                continue

            if _NAV_PRIORITY_RE.search(text):
                priority = 0
            elif _FINAL_PRIORITY_RE.search(text):
                priority = 2
            elif _ACTION_PRIORITY_RE.search(text):
                priority = 1
            else:
                priority = 3

            identity = " ".join(
                str(button.get(key) or "")
                for key in ("id", "name", "className", "type")
            ).lower()
            submit_like = 1 if (
                str(button.get("type") or "").lower() == "submit"
                or "submit" in identity
                or "btn-main" in identity
            ) else 0
            inside_form = 1 if button.get("insideForm") or button.get("inside_form") else 0
            score = (priority, -submit_like, -inside_form)
            enriched = dict(button)
            enriched["_next_score"] = score
            candidates.append(enriched)

        candidates.sort(key=lambda item: item.get("_next_score") or (9, 0, 0))
        return candidates

    def find_next_button(self, dom: dict[str, Any]) -> Optional[dict[str, Any]]:
        candidates = self.next_candidates(dom)
        if not candidates:
            return None
        best_score = candidates[0].get("_next_score")
        best = [item for item in candidates if item.get("_next_score") == best_score]
        if len(best) != 1:
            # Responsive portals often render the same action twice (mobile and
            # desktop).  Identical text + href is one action, not a choice.
            distinct = {
                (
                    re.sub(r"\s+", " ", str(item.get("text") or "")).strip().lower(),
                    str(item.get("href") or ""),
                )
                for item in best
            }
            if len(distinct) != 1:
                # Two different controls are equally valid.  Do not pick one.
                return None
            best.sort(key=lambda item: str(item.get("element_id") or item.get("id") or ""))
        chosen = dict(best[0])
        chosen.pop("_next_score", None)
        return chosen

    def find_gateway(self, dom: dict[str, Any], gateway_type: str) -> Optional[dict[str, Any]]:
        for gateway in dom.get("gateways") or []:
            if gateway.get("type") != gateway_type:
                continue
            if gateway.get("visible") is False or gateway.get("interactable") is False:
                continue
            if gateway.get("covered_by"):
                continue
            return gateway
        return None


class SimulatorAdapter(BasePortalAdapter):
    name = "simulator"

    def current_step(self, page: Page, dom: dict[str, Any]) -> int:
        active = str(dom.get("activeSectionId") or "")
        if active.startswith("sec-"):
            try:
                return int(active.split("-", 1)[1])
            except ValueError:
                pass
        return super().current_step(page, dom)

    def is_payment_page(self, page: Page, dom: dict[str, Any]) -> bool:
        return bool(dom.get("activeSectionId") == "sec-4" or dom.get("hasPaymentButton"))

    async def wait_for_step_change(
        self,
        page: Page,
        previous_step: int,
        *,
        timeout_ms: int = 12000,
        before: Optional[dict[str, Any]] = None,
    ) -> bool:
        target = previous_step + 1
        selectors = ["#dashboard-view"]
        if 1 <= target <= 4:
            selectors.append(f"#sec-{target}.active")
        # A comma-separated selector can resolve to the first DOM match (a
        # hidden element) and then wait forever. Check each candidate
        # explicitly so a visible section *or* the signed-in dashboard counts.
        try:
            await page.wait_for_function(
                """(selectors) => selectors.some((selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                })""",
                arg=selectors,
                timeout=timeout_ms,
            )
            return True
        except Exception:
            return False

    def find_next_button(self, dom: dict[str, Any]) -> Optional[dict[str, Any]]:
        step = self.current_step_from_dom(dom)
        expected_id = f"btn-save-next-{step}"
        for button in dom.get("nextButtons") or []:
            if button.get("id") == expected_id:
                return button
        return super().find_next_button(dom)

    @staticmethod
    def current_step_from_dom(dom: dict[str, Any]) -> int:
        active = str(dom.get("activeSectionId") or "")
        if active.startswith("sec-"):
            try:
                return int(active.split("-", 1)[1])
            except ValueError:
                pass
        return 1


def get_adapter(url: str) -> BasePortalAdapter:
    clean_url = (url or "").lower()
    if "gov-portal-demo" in clean_url or "gov-portal-simulator" in clean_url:
        return SimulatorAdapter()
    return BasePortalAdapter()
