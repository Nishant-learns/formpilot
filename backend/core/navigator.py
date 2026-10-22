import asyncio
import time
from typing import Dict, Any, Optional
from playwright.async_api import Page, Error as PlaywrightError

class ResilientNavigator:
    """Non-blocking resilient navigation engine with adaptive hydration & context recovery."""

    @classmethod
    async def navigate_safely(
        cls,
        page: Page,
        url: str,
        timeout_ms: int = 45000,
        max_hydration_wait_ms: int = 15000
    ) -> Dict[str, Any]:
        """
        Navigates using non-blocking commit, awaits DOMContentLoaded,
        and uses an adaptive hydration observation loop to catch client redirection context destructions.
        """
        start_time = time.time()
        
        # Step 1: Non-blocking commit
        try:
            response = await page.goto(url, wait_until="commit", timeout=timeout_ms)
            status_code = response.status if response else 200
        except PlaywrightError as pe:
            # Handle client-side immediate redirect
            if "net::ERR_ABORTED" in str(pe) or "Execution context was destroyed" in str(pe):
                # Absorb redirect and wait for target context
                await asyncio.sleep(1.0)
                status_code = 200
            else:
                raise pe

        # Step 2: Await DOM Content Loaded
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass  # Proceed to adaptive observation loop

        # Step 3: Adaptive Hydration Observation Loop
        hydrated = False
        last_elem_count = 0
        stable_cycles = 0
        loop_start = time.time()

        while (time.time() - loop_start) * 1000 < max_hydration_wait_ms:
            try:
                state_info = await page.evaluate("""
                () => {
                    // Check ASP.NET async postback
                    const isAspBusy = window.Sys && window.Sys.WebForms && window.Sys.WebForms.PageRequestManager && window.Sys.WebForms.PageRequestManager.getInstance().get_isInAsyncPostBack();
                    // Check jQuery active
                    const isJqBusy = window.jQuery && window.jQuery.active > 0;
                    // Count interactive inputs
                    const inputs = document.querySelectorAll('input, select, textarea, button, a').length;
                    return {
                        readyState: document.readyState,
                        isBusy: Boolean(isAspBusy || isJqBusy),
                        elemCount: inputs
                    };
                }
                """)

                # If DOM is interactive or complete and element count has stabilized
                if state_info.get("readyState") in ("interactive", "complete") and not state_info.get("isBusy"):
                    elem_count = state_info.get("elemCount", 0)
                    if elem_count > 0 and elem_count == last_elem_count:
                        stable_cycles += 1
                        if stable_cycles >= 2:  # Stabilized across consecutive observations
                            hydrated = True
                            break
                    else:
                        stable_cycles = 0
                        last_elem_count = elem_count
            except PlaywrightError as pe:
                # Execution context destroyed by client redirection (e.g., SPA route change)
                if "Execution context was destroyed" in str(pe) or "Target closed" in str(pe):
                    await asyncio.sleep(0.5)
                    continue
                else:
                    break
            except Exception:
                break

            await asyncio.sleep(0.4)

        elapsed = round(time.time() - start_time, 2)
        return {
            "success": True,
            "url": page.url,
            "status_code": status_code,
            "elapsed_seconds": elapsed,
            "hydrated": hydrated
        }

    @classmethod
    async def capture_high_res_screenshot(cls, page: Page) -> bytes:
        """Captures clear full viewport screenshot for the candidate Cockpit stream."""
        try:
            return await page.screenshot(type="jpeg", quality=85, full_page=False)
        except Exception as e:
            print(f"[ResilientNavigator] Screenshot error: {e}")
            return b""
