"""Deterministic action execution against a DOM blueprint.

The resolver is the only component that touches the live page.  It receives a
blueprint element id, finds exactly one matching element in the correct frame,
validates it, checks actionability and only then acts.

It deliberately does *not* click by visible text as a first strategy.  Text is
a last-resort disambiguator after the unique id, CSS and XPath have failed.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from playwright.async_api import Frame, Locator, Page

from .blueprint import BlueprintElement, PageBlueprint


class Postcondition(str, Enum):
    """What the page said after an action, not just whether it was dispatched.

    A dispatched click is not a committed action.  Skyvern learned this the
    hard way: ``locator.click`` returning is evidence that the event was sent,
    not that the portal accepted it.  Each action type gets the check that
    actually means something for it:

    * ``HELD`` — a typed control holds the requested value or state.
    * ``CHANGED`` — the page identity, text or field structure moved.
    * ``NO_CHANGE`` — the click was dispatched and nothing changed.
    * ``NOT_HELD`` — the control reverted or refused the value.
    * ``UNVERIFIED`` — the page could not be read; say so instead of guessing.
    """

    HELD = "held"
    CHANGED = "changed"
    NO_CHANGE = "no_change"
    NOT_HELD = "not_held"
    UNVERIFIED = "unverified"


class ResolverError(RuntimeError):
    """A structured resolver failure with a stable error code."""

    def __init__(self, code: str, message: str, *, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class ActionResult:
    ok: bool
    action: str
    element_id: str = ""
    method: str = ""
    message: str = ""
    error_code: str = ""
    drift: bool = False
    attempts: int = 1
    scan_id: str = ""
    postcondition: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "element_id": self.element_id,
            "method": self.method,
            "message": self.message,
            "error_code": self.error_code,
            "drift": self.drift,
            "attempts": self.attempts,
            "scan_id": self.scan_id,
            "postcondition": self.postcondition,
            "details": self.details,
        }


def _css_attr(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


class ActionResolver:
    """Resolve blueprint ids and perform safe Playwright actions."""

    def __init__(
        self,
        page: Page,
        blueprint: PageBlueprint,
        *,
        timeout_ms: int = 8000,
        rescan: Optional[Callable[[], Awaitable[PageBlueprint]]] = None,
    ):
        self.page = page
        self.blueprint = blueprint
        self.timeout_ms = timeout_ms
        self.rescan = rescan

    # ------------------------------------------------------------------ frames

    def _frame_for(self, element: BlueprintElement) -> Optional[Frame]:
        frames = list(self.page.frames or [])
        if element.frame == "main":
            return self.page.main_frame
        if 0 <= element.frame_index < len(frames):
            frame = frames[element.frame_index]
            # A frame index can shift after a navigation.  Prefer the recorded
            # URL/name when they are available and disagree.
            info = next(
                (item for item in self.blueprint.frames if item.get("id") == element.frame),
                None,
            )
            if info and info.get("url") and frame.url and frame.url != info.get("url"):
                for candidate in frames:
                    if candidate.url == info.get("url"):
                        return candidate
            return frame
        for info in self.blueprint.frames:
            if info.get("id") != element.frame:
                continue
            for frame in frames:
                if info.get("url") and frame.url == info.get("url"):
                    return frame
                if info.get("name") and frame.name == info.get("name"):
                    return frame
        return None

    # ------------------------------------------------------------------ resolve

    def _candidate_locators(self, frame: Frame, element: BlueprintElement):
        """Yield (strategy, locator) in priority order."""
        if element.id:
            yield "blueprint_id", frame.locator(f'[data-fp-id="{_css_attr(element.id)}"]')
        if element.css and element.css_unique:
            yield "css", frame.locator(element.css)
        if element.xpath:
            yield "xpath", frame.locator(f"xpath={element.xpath}")
        if element.role and element.name:
            yield "role_name", frame.get_by_role(element.role, name=element.name, exact=True)
        name_attr = element.attributes.get("name")
        if name_attr:
            tag = element.tag or "*"
            yield "name_attr", frame.locator(f'{tag}[name="{_css_attr(name_attr)}"]')
        if element.name and element.tag in {"input", "select", "textarea"}:
            yield "label", frame.get_by_label(element.name, exact=True)
        # Last resort: a unique tag + exact text match.  The count check below
        # rejects ambiguous matches; we never call .first.
        if element.name and element.tag:
            yield "tag_text", frame.locator(
                f'{element.tag}:text-is("{_css_attr(element.name)}")'
            )

    async def resolve(self, element_id: str) -> Tuple[Frame, Locator, BlueprintElement, str]:
        element = self.blueprint.get(element_id)
        if not element:
            raise ResolverError(
                "NOT_FOUND",
                f"Element {element_id} is not present in the current blueprint.",
            )
        frame = self._frame_for(element)
        if frame is None:
            raise ResolverError(
                "FRAME_NOT_ACCESSIBLE",
                f"The frame for {element.label!r} is no longer available.",
                details={"frame": element.frame},
            )

        counts: Dict[str, int] = {}
        errors: List[str] = []
        for strategy, locator in self._candidate_locators(frame, element):
            try:
                count = await locator.count()
            except Exception as exc:
                errors.append(f"{strategy}: {str(exc)[:120]}")
                continue
            counts[strategy] = count
            if count == 1:
                return frame, locator, element, strategy
            if count > 1:
                errors.append(f"{strategy}: {count} matches")
            else:
                errors.append(f"{strategy}: 0 matches")

        if any(count > 1 for count in counts.values()):
            raise ResolverError(
                "MULTIPLE_MATCHES",
                f"{element.label!r} is ambiguous on the page. Refusing to guess.",
                details={"counts": counts, "errors": errors},
            )
        raise ResolverError(
            "NOT_FOUND",
            f"{element.label!r} could not be found on the page.",
            details={"counts": counts, "errors": errors},
        )

    # ------------------------------------------------------------------ checks

    async def _scroll(self, locator: Locator) -> None:
        try:
            await locator.scroll_into_view_if_needed(timeout=min(self.timeout_ms, 5000))
        except Exception:
            pass

    async def _is_visible(self, locator: Locator) -> bool:
        try:
            return bool(await locator.is_visible())
        except Exception:
            return False

    async def _is_enabled(self, locator: Locator) -> bool:
        try:
            return bool(await locator.is_enabled())
        except Exception:
            return True

    async def _is_editable(self, locator: Locator) -> bool:
        try:
            return bool(await locator.is_editable())
        except Exception:
            return True

    async def _hit_test(self, locator: Locator) -> Optional[Dict[str, Any]]:
        """Return the covering element, or None when the target is clickable."""
        try:
            return await locator.evaluate(
                """el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) return null;
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) return null;
                    const hit = document.elementFromPoint(x, y);
                    if (!hit) return null;
                    if (hit === el || el.contains(hit) || hit.contains(el)) return null;
                    const label = hit.closest && hit.closest('label');
                    if (label && label.contains(el)) return null;
                    return {
                        tag: hit.tagName.toLowerCase(),
                        id: hit.id || null,
                        className: String(hit.className || '').slice(0, 120),
                        text: (hit.innerText || hit.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 120),
                    };
                }"""
            )
        except Exception:
            return None

    async def _tag(self, locator: Locator) -> str:
        try:
            return str(await locator.evaluate("el => el.tagName.toLowerCase()"))
        except Exception:
            return ""

    # --------------------------------------------------------- post-conditions

    # A cheap page identity: URL, title, a text digest, the visible field
    # structure and the values.  Deliberately not the full DOM scan — this runs
    # after every click.
    _PAGE_STATE_JS = r"""
    () => {
        const visible = (el) => el && el.getClientRects().length > 0;
        const text = (document.body && document.body.innerText
            ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
        let digest = 0;
        for (let i = 0; i < text.length && i < 2000; i += 1) {
            digest = ((digest << 5) - digest + text.charCodeAt(i)) | 0;
        }
        const fields = Array.from(document.querySelectorAll(
            'input:not([type="hidden"]), select, textarea'
        )).filter(visible);
        return {
            url: location.href,
            title: document.title || '',
            textDigest: String(digest),
            textLength: text.length,
            fieldCount: fields.length,
            fields: fields.map((el) => [
                el.tagName.toLowerCase(),
                el.getAttribute('name') || '',
                String(el.value || ''),
                el.checked ? '1' : '0',
                String(el.selectedIndex === undefined ? '' : el.selectedIndex),
            ].join(':')).join('|'),
        };
    }
    """

    async def _page_state(self) -> Optional[Dict[str, Any]]:
        """The page identity, or ``None`` when it cannot be read."""
        try:
            state = await self.page.evaluate(self._PAGE_STATE_JS)
        except Exception:
            return None
        return state if isinstance(state, dict) else None

    @staticmethod
    def _state_changed(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
        keys = ("url", "title", "textDigest", "textLength", "fieldCount", "fields")
        return any(str(before.get(key) or "") != str(after.get(key) or "") for key in keys)

    async def _settle(
        self,
        before: Optional[Dict[str, Any]],
        *,
        timeout_ms: int = 600,
    ) -> Postcondition:
        """Wait briefly for a click to show an effect, then say what happened."""
        if not before:
            return Postcondition.UNVERIFIED
        before_url = str(before.get("url") or "")
        deadline = asyncio.get_running_loop().time() + max(0.0, timeout_ms / 1000)
        while True:
            after = await self._page_state()
            if after is None:
                # A navigation can destroy the execution context mid-read.
                try:
                    if before_url and self.page.url != before_url:
                        return Postcondition.CHANGED
                except Exception:
                    pass
            elif self._state_changed(before, after):
                return Postcondition.CHANGED
            if asyncio.get_running_loop().time() >= deadline:
                return Postcondition.NO_CHANGE
            await asyncio.sleep(0.1)

    @staticmethod
    def _click_result(
        result: ActionResult,
        verdict: Postcondition,
    ) -> ActionResult:
        result.postcondition = verdict.value
        result.details = {**(result.details or {}), "postcondition": verdict.value}
        return result

    # ------------------------------------------------------------------ click

    async def click(self, element_id: str) -> ActionResult:
        action = "click"
        try:
            before_url = self.page.url
        except Exception:
            before_url = ""

        def navigated() -> bool:
            """True when the click already moved the page.

            A link click can navigate before Playwright returns, which makes
            ``locator.click`` raise even though the action succeeded.  Treating
            that as a failure sends the agent into fallback clicks on the new
            page and loses the navigation.
            """
            if not before_url:
                return False
            try:
                return self.page.url != before_url
            except Exception:
                return False

        try:
            frame, locator, element, strategy = await self.resolve(element_id)
        except ResolverError as exc:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code=exc.code,
                message=exc.message,
                scan_id=self.blueprint.scan_id,
                details=exc.details,
            )

        await self._scroll(locator)
        tag = await self._tag(locator)
        if element.tag and tag and tag != element.tag:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="DRIFT",
                message=(
                    f"The element at {strategy} changed from <{element.tag}> to "
                    f"<{tag}>. Refusing to click a different control."
                ),
                drift=True,
                scan_id=self.blueprint.scan_id,
            )
        if not await self._is_visible(locator):
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="NOT_VISIBLE",
                message=f"{element.label!r} is not visible.",
                scan_id=self.blueprint.scan_id,
            )
        if not await self._is_enabled(locator):
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="DISABLED",
                message=f"{element.label!r} is disabled.",
                scan_id=self.blueprint.scan_id,
            )

        covered = await self._hit_test(locator)
        if covered:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="COVERED",
                message=(
                    f"{element.label!r} is covered by "
                    f"<{covered.get('tag')}> {covered.get('text') or ''}".strip()
                ),
                scan_id=self.blueprint.scan_id,
                details={"covered_by": covered, "strategy": strategy},
            )

        attempts: List[Dict[str, str]] = []
        before_state = await self._page_state()
        try:
            await locator.click(timeout=self.timeout_ms)
            return self._click_result(
                ActionResult(
                    ok=True,
                    action=action,
                    element_id=element_id,
                    method=f"playwright:{strategy}",
                    message=f"Clicked {element.label!r}.",
                    scan_id=self.blueprint.scan_id,
                ),
                await self._settle(before_state),
            )
        except Exception as exc:
            attempts.append({"method": "playwright", "error": str(exc)[:240]})
            if navigated():
                return self._click_result(
                    ActionResult(
                        ok=True,
                        action=action,
                        element_id=element_id,
                        method=f"playwright:navigated:{strategy}",
                        message=f"Clicked {element.label!r} and the page moved.",
                        scan_id=self.blueprint.scan_id,
                        details={"attempts": attempts},
                    ),
                    Postcondition.CHANGED,
                )

        # A coordinate click is useful when a framework intercepts the
        # synthetic click but the point itself is not covered.
        try:
            box = await locator.bounding_box()
            if box:
                await self.page.mouse.click(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                )
                return self._click_result(
                    ActionResult(
                        ok=True,
                        action=action,
                        element_id=element_id,
                        method=f"mouse:{strategy}",
                        message=f"Clicked {element.label!r} at its screen position.",
                        scan_id=self.blueprint.scan_id,
                        details={"attempts": attempts},
                    ),
                    await self._settle(before_state),
                )
        except Exception as exc:
            attempts.append({"method": "mouse", "error": str(exc)[:240]})
            if navigated():
                return self._click_result(
                    ActionResult(
                        ok=True,
                        action=action,
                        element_id=element_id,
                        method=f"mouse:navigated:{strategy}",
                        message=f"Clicked {element.label!r} at its screen position and the page moved.",
                        scan_id=self.blueprint.scan_id,
                        details={"attempts": attempts},
                    ),
                    Postcondition.CHANGED,
                )

        # Last resort: a JS click, but only when the target is still the
        # element under its own centre point.  Never bypass a real overlay.
        covered = await self._hit_test(locator)
        if covered:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="COVERED",
                message=(
                    f"{element.label!r} is covered by "
                    f"<{covered.get('tag')}> {covered.get('text') or ''}".strip()
                ),
                scan_id=self.blueprint.scan_id,
                details={"covered_by": covered, "attempts": attempts, "strategy": strategy},
            )
        try:
            await locator.evaluate("el => el.click()")
            return self._click_result(
                ActionResult(
                    ok=True,
                    action=action,
                    element_id=element_id,
                    method=f"js:{strategy}",
                    message=f"Clicked {element.label!r} with a DOM click.",
                    scan_id=self.blueprint.scan_id,
                    details={"attempts": attempts},
                ),
                await self._settle(before_state),
            )
        except Exception as exc:
            attempts.append({"method": "js", "error": str(exc)[:240]})
            if navigated():
                return self._click_result(
                    ActionResult(
                        ok=True,
                        action=action,
                        element_id=element_id,
                        method=f"js:navigated:{strategy}",
                        message=f"Clicked {element.label!r} with a DOM click and the page moved.",
                        scan_id=self.blueprint.scan_id,
                        details={"attempts": attempts},
                    ),
                    Postcondition.CHANGED,
                )

        return ActionResult(
            ok=False,
            action=action,
            element_id=element_id,
            error_code="CLICK_FAILED",
            message=f"Could not click {element.label!r}.",
            scan_id=self.blueprint.scan_id,
            details={"attempts": attempts, "strategy": strategy},
        )

    # ------------------------------------------------------------------ fill

    async def fill(self, element_id: str, value: str) -> ActionResult:
        action = "fill"
        try:
            frame, locator, element, strategy = await self.resolve(element_id)
        except ResolverError as exc:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code=exc.code,
                message=exc.message,
                scan_id=self.blueprint.scan_id,
                details=exc.details,
            )

        await self._scroll(locator)
        if not await self._is_visible(locator):
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="NOT_VISIBLE",
                message=f"{element.label!r} is not visible.",
                scan_id=self.blueprint.scan_id,
            )
        if not await self._is_enabled(locator):
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="DISABLED",
                message=f"{element.label!r} is disabled.",
                scan_id=self.blueprint.scan_id,
            )
        if not await self._is_editable(locator):
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="NOT_EDITABLE",
                message=f"{element.label!r} is read-only.",
                scan_id=self.blueprint.scan_id,
            )

        text = str(value)
        if element.tag == "input" and str(element.attributes.get("type") or "").lower() == "date":
            match = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", text.strip())
            if match:
                text = f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}"
        attempts: List[Dict[str, str]] = []

        # Native fill is fastest and dispatches input/change for React.
        try:
            await locator.fill(text, timeout=self.timeout_ms)
            if await self._value_matches(locator, element, text):
                return ActionResult(
                    ok=True,
                    action=action,
                    element_id=element_id,
                    method=f"fill:{strategy}",
                    message=f"Filled {element.label!r}.",
                    scan_id=self.blueprint.scan_id,
                    postcondition=Postcondition.HELD.value,
                )
            attempts.append({"method": "fill", "error": "value did not stick"})
        except Exception as exc:
            attempts.append({"method": "fill", "error": str(exc)[:240]})

        # Typing is slower but works with masks and autocomplete widgets.
        try:
            await locator.click(timeout=self.timeout_ms)
            await locator.press("Control+A")
            await locator.press_sequentially(text, delay=8, timeout=self.timeout_ms)
            if await self._value_matches(locator, element, text):
                return ActionResult(
                    ok=True,
                    action=action,
                    element_id=element_id,
                    method=f"type:{strategy}",
                    message=f"Typed into {element.label!r}.",
                    scan_id=self.blueprint.scan_id,
                    postcondition=Postcondition.HELD.value,
                    details={"attempts": attempts},
                )
            attempts.append({"method": "type", "error": "value did not stick"})
        except Exception as exc:
            attempts.append({"method": "type", "error": str(exc)[:240]})

        # JS setter fallback for controlled inputs that ignore Playwright.
        try:
            result = await locator.evaluate(
                """(el, value) => {
                    el.focus();
                    if (el.isContentEditable) {
                        el.innerText = value;
                    } else {
                        const proto = el.tagName.toLowerCase() === 'textarea'
                            ? HTMLTextAreaElement.prototype
                            : HTMLInputElement.prototype;
                        const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                        if (descriptor && descriptor.set) descriptor.set.call(el, value);
                        else el.value = value;
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                    return true;
                }""",
                text,
            )
            if result and await self._value_matches(locator, element, text):
                return ActionResult(
                    ok=True,
                    action=action,
                    element_id=element_id,
                    method=f"js:{strategy}",
                    message=f"Filled {element.label!r} with a DOM setter.",
                    scan_id=self.blueprint.scan_id,
                    postcondition=Postcondition.HELD.value,
                    details={"attempts": attempts},
                )
        except Exception as exc:
            attempts.append({"method": "js", "error": str(exc)[:240]})

        return ActionResult(
            ok=False,
            action=action,
            element_id=element_id,
            error_code="FILL_FAILED",
            message=f"Could not fill {element.label!r}.",
            scan_id=self.blueprint.scan_id,
            postcondition=Postcondition.NOT_HELD.value,
            details={"attempts": attempts, "strategy": strategy},
        )

    async def _value_matches(
        self, locator: Locator, element: BlueprintElement, expected: str
    ) -> bool:
        try:
            if element.tag in {"input", "textarea", "select"}:
                actual = await locator.input_value(timeout=2000)
            else:
                actual = await locator.inner_text(timeout=2000)
        except Exception:
            return False
        return str(actual or "").strip() == str(expected or "").strip()

    @staticmethod
    def _normalized(value: Any) -> str:
        return re.sub(r"\s+", "", str(value or "")).casefold()

    async def _selected_matches(self, locator: Locator, target: str) -> bool:
        """True when the select now holds the requested value *or* option text."""
        wanted = self._normalized(target)
        if not wanted:
            return False
        try:
            value = await locator.input_value(timeout=2000)
        except Exception:
            value = ""
        try:
            text = await locator.evaluate(
                "el => (el.options && el.selectedIndex >= 0)"
                " ? el.options[el.selectedIndex].text : ''"
            )
        except Exception:
            text = ""
        return wanted in {self._normalized(value), self._normalized(text)}

    # ------------------------------------------------------------------ select

    async def select(self, element_id: str, value: str) -> ActionResult:
        action = "select"
        try:
            frame, locator, element, strategy = await self.resolve(element_id)
        except ResolverError as exc:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code=exc.code,
                message=exc.message,
                scan_id=self.blueprint.scan_id,
                details=exc.details,
            )

        await self._scroll(locator)
        if not await self._is_visible(locator):
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="NOT_VISIBLE",
                message=f"{element.label!r} is not visible.",
                scan_id=self.blueprint.scan_id,
            )

        target = str(value or "").strip()
        attempts: List[Dict[str, str]] = []
        for kwargs in ({"label": target}, {"value": target}):
            try:
                await locator.select_option(**kwargs, timeout=self.timeout_ms)
                if await self._selected_matches(locator, target):
                    return ActionResult(
                        ok=True,
                        action=action,
                        element_id=element_id,
                        method=f"select_option:{strategy}",
                        message=f"Selected {target!r} in {element.label!r}.",
                        scan_id=self.blueprint.scan_id,
                        postcondition=Postcondition.HELD.value,
                        details={"attempts": attempts},
                    )
                attempts.append(
                    {
                        "method": f"select_option:{list(kwargs)[0]}",
                        "error": "the select did not keep the value",
                    }
                )
            except Exception as exc:
                attempts.append({"method": f"select_option:{list(kwargs)[0]}", "error": str(exc)[:240]})

        # Match by visible option text, then by value, then by index.
        normalized = target.lower().replace(" ", "")
        option = None
        for item in element.options:
            if (
                str(item.get("text") or "").lower().replace(" ", "") == normalized
                or str(item.get("value") or "").lower().replace(" ", "") == normalized
            ):
                option = item
                break
        if option is not None:
            try:
                await locator.select_option(index=int(option.get("index") or 0), timeout=self.timeout_ms)
                if await self._selected_matches(locator, target) or await self._selected_matches(
                    locator, str(option.get("text") or "")
                ):
                    return ActionResult(
                        ok=True,
                        action=action,
                        element_id=element_id,
                        method=f"select_index:{strategy}",
                        message=f"Selected {option.get('text')!r} in {element.label!r}.",
                        scan_id=self.blueprint.scan_id,
                        postcondition=Postcondition.HELD.value,
                        details={"attempts": attempts},
                    )
                attempts.append({"method": "select_index", "error": "the select did not keep the value"})
            except Exception as exc:
                attempts.append({"method": "select_index", "error": str(exc)[:240]})

        return ActionResult(
            ok=False,
            action=action,
            element_id=element_id,
            error_code="SELECT_NOT_HELD",
            message=f"The select {element.label!r} did not keep {target!r}.",
            scan_id=self.blueprint.scan_id,
            postcondition=Postcondition.NOT_HELD.value,
            details={"attempts": attempts, "options": element.options[:20]},
        )

    # ------------------------------------------------------------------ check

    async def check(self, element_id: str, checked: bool = True) -> ActionResult:
        action = "check" if checked else "uncheck"
        try:
            frame, locator, element, strategy = await self.resolve(element_id)
        except ResolverError as exc:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code=exc.code,
                message=exc.message,
                scan_id=self.blueprint.scan_id,
                details=exc.details,
            )

        await self._scroll(locator)

        async def holds() -> bool:
            try:
                return bool(await locator.is_checked(timeout=2000)) is bool(checked)
            except Exception:
                return False

        try:
            if checked:
                await locator.check(timeout=self.timeout_ms)
            else:
                await locator.uncheck(timeout=self.timeout_ms)
            if await holds():
                return ActionResult(
                    ok=True,
                    action=action,
                    element_id=element_id,
                    method=f"check:{strategy}",
                    message=f"{'Checked' if checked else 'Unchecked'} {element.label!r}.",
                    scan_id=self.blueprint.scan_id,
                    postcondition=Postcondition.HELD.value,
                )
        except Exception as exc:
            try:
                await locator.evaluate(
                    "(el, value) => { el.checked = value; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                    checked,
                )
                if await holds():
                    return ActionResult(
                        ok=True,
                        action=action,
                        element_id=element_id,
                        method=f"js:{strategy}",
                        message=f"{'Checked' if checked else 'Unchecked'} {element.label!r} with a DOM setter.",
                        scan_id=self.blueprint.scan_id,
                        postcondition=Postcondition.HELD.value,
                    )
            except Exception:
                pass
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="CHECK_NOT_HELD",
                message=(
                    f"Could not {'check' if checked else 'uncheck'} {element.label!r}: "
                    "the control did not keep the state."
                ),
                scan_id=self.blueprint.scan_id,
                postcondition=Postcondition.NOT_HELD.value,
                details={"attempts": [{"method": "check", "error": str(exc)[:240]}]},
            )

        # The click path returned without raising but the state did not stick.
        try:
            await locator.evaluate(
                "(el, value) => { el.checked = value; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                checked,
            )
            if await holds():
                return ActionResult(
                    ok=True,
                    action=action,
                    element_id=element_id,
                    method=f"js:{strategy}",
                    message=f"{'Checked' if checked else 'Unchecked'} {element.label!r} with a DOM setter.",
                    scan_id=self.blueprint.scan_id,
                    postcondition=Postcondition.HELD.value,
                )
        except Exception:
            pass
        return ActionResult(
            ok=False,
            action=action,
            element_id=element_id,
            error_code="CHECK_NOT_HELD",
            message=(
                f"Could not {'check' if checked else 'uncheck'} {element.label!r}: "
                "the control did not keep the state."
            ),
            scan_id=self.blueprint.scan_id,
            postcondition=Postcondition.NOT_HELD.value,
        )

    # ------------------------------------------------------------------ upload

    async def upload(self, element_id: str, path: str) -> ActionResult:
        action = "upload"
        try:
            frame, locator, element, strategy = await self.resolve(element_id)
        except ResolverError as exc:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code=exc.code,
                message=exc.message,
                scan_id=self.blueprint.scan_id,
                details=exc.details,
            )
        try:
            await locator.set_input_files(str(path), timeout=max(self.timeout_ms, 15000))
        except Exception as exc:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="UPLOAD_FAILED",
                message=f"Could not attach the file to {element.label!r}: {str(exc)[:160]}",
                scan_id=self.blueprint.scan_id,
            )
        # The file picker accepting a path is not the same as the input holding
        # the file: a framework can clear it on change.
        try:
            names = await locator.evaluate(
                "el => Array.from(el.files || []).map((file) => file.name)"
            )
        except Exception:
            names = None
        if isinstance(names, list):
            expected = os.path.basename(str(path))
            if not names:
                return ActionResult(
                    ok=False,
                    action=action,
                    element_id=element_id,
                    error_code="UPLOAD_NOT_HELD",
                    message=f"The file input {element.label!r} did not keep the file.",
                    scan_id=self.blueprint.scan_id,
                    postcondition=Postcondition.NOT_HELD.value,
                )
            if expected and expected not in names:
                return ActionResult(
                    ok=False,
                    action=action,
                    element_id=element_id,
                    error_code="UPLOAD_NOT_HELD",
                    message=(
                        f"The file input {element.label!r} holds a different file "
                        f"({', '.join(str(name) for name in names[:3])})."
                    ),
                    scan_id=self.blueprint.scan_id,
                    postcondition=Postcondition.NOT_HELD.value,
                    details={"held": names[:5]},
                )
        return ActionResult(
            ok=True,
            action=action,
            element_id=element_id,
            method=f"set_input_files:{strategy}",
            message=f"Attached {os.path.basename(str(path))} to {element.label!r}.",
            scan_id=self.blueprint.scan_id,
            postcondition=(
                Postcondition.HELD.value if isinstance(names, list) else Postcondition.UNVERIFIED.value
            ),
        )

    # ------------------------------------------------------------------ press

    async def press(self, element_id: str, key: str) -> ActionResult:
        action = "press"
        try:
            frame, locator, element, strategy = await self.resolve(element_id)
        except ResolverError as exc:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code=exc.code,
                message=exc.message,
                scan_id=self.blueprint.scan_id,
                details=exc.details,
            )
        before_state = await self._page_state()
        try:
            await locator.press(key, timeout=self.timeout_ms)
            return self._click_result(
                ActionResult(
                    ok=True,
                    action=action,
                    element_id=element_id,
                    method=f"press:{strategy}",
                    message=f"Pressed {key} on {element.label!r}.",
                    scan_id=self.blueprint.scan_id,
                ),
                await self._settle(before_state),
            )
        except Exception as exc:
            return ActionResult(
                ok=False,
                action=action,
                element_id=element_id,
                error_code="PRESS_FAILED",
                message=f"Could not press {key} on {element.label!r}: {str(exc)[:160]}",
                scan_id=self.blueprint.scan_id,
            )
