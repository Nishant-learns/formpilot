"""Portal-specific hints on top of the universal DOM scanner.

The orchestrator works on any HTML form.  Adapters only answer a few
questions that are expensive or ambiguous to infer from raw DOM: what step is
this, is this the payment page, and which button advances the flow.
"""

from __future__ import annotations

from typing import Any, Optional

from playwright.async_api import Page


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

    async def wait_for_step_change(
        self,
        page: Page,
        previous_step: int,
        *,
        timeout_ms: int = 12000,
    ) -> bool:
        try:
            await page.wait_for_timeout(400)
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass
        return True

    def find_next_button(self, dom: dict[str, Any]) -> Optional[dict[str, Any]]:
        buttons = dom.get("nextButtons") or []
        for button in reversed(buttons):
            text = str(button.get("text") or "").lower()
            if "back" in text or "previous" in text:
                continue
            return button
        return None

    def find_gateway(self, dom: dict[str, Any], gateway_type: str) -> Optional[dict[str, Any]]:
        for gateway in dom.get("gateways") or []:
            if gateway.get("type") == gateway_type:
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
    if "gov-portal-demo" in (url or ""):
        return SimulatorAdapter()
    return BasePortalAdapter()
