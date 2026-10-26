"""Deterministic portal recipes and drift detection.

A recipe is *not* a recording of values.  It is a compact, reviewable map of a
page: canonical field keys, locator strategies, page type and a structural
fingerprint.  Values stay in the vault; screenshots and raw DOM stay in the
run trace.

The runtime always observes the live page.  A recipe records what was observed
on a previous visit so the next visit can be compared, but a stale recipe must
never win over what the page actually says.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from . import settings
from .form_model import FormModel, _norm_name, _norm_text


# Two pages are the same logical step when most replayable field keys overlap.
# Different active sections or form actions are strong evidence that they are
# different steps.  A heading alone is weak: many portals reuse one generic
# heading (or none at all) across every step.
_SIMILARITY_THRESHOLD = 0.6
_STEP_NUMBER_RE = re.compile(
    r"\b(?:stage|step|phase|section|part)\s*[-:#.]?\s*\d+\b", re.IGNORECASE
)


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _safe_file_part(value: str) -> str:
    text = re.sub(r"[^a-z0-9._-]+", "_", (value or "").lower()).strip("._-")
    return text[:120] or "portal"


def _normalize_id(value: str) -> str:
    """Normalize a recipe id without truncating it (ids can be 180 chars)."""
    return re.sub(r"[^a-z0-9._-]+", "_", (value or "").lower()).strip("._-")


def _bounded_id(value: str, limit: int = 180) -> str:
    """Keep a recipe id usable as one file name on common filesystems."""
    if len(value) <= limit:
        return value
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{value[: limit - 11]}_{digest}"


def _action_path(value: Any) -> str:
    """Return the path part of a form action, ignoring query and fragment."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return ""
    path = parsed.path or ""
    if not path or path == "/":
        return ""
    return path


def page_key_for(form_map: Dict[str, Any]) -> str:
    """Identify one visible step of a portal, not just ``portal + page_type``.

    The key combines whatever step signals the page exposes:

    * the visible step heading (with "Stage 2:" style numbering removed)
    * the active section id (``sec-2``, ``step-address``, ...)
    * the path of the form action

    Pages without any step signal keep the legacy identity so existing
    ``portal__page_type`` recipes remain readable.
    """
    heading = _norm_text(form_map.get("step_heading"))
    heading = _STEP_NUMBER_RE.sub(" ", heading)
    heading = re.sub(r"\s+", " ", heading).strip()

    parts: List[str] = []
    if heading:
        parts.append(f"step_{_safe_file_part(heading)[:60]}")
    section_id = _norm_text(form_map.get("active_section_id"))
    if section_id:
        parts.append(f"sec_{_safe_file_part(section_id)}")
    action = _action_path(form_map.get("form_action"))
    if action:
        parts.append(f"action_{_safe_file_part(action.replace('/', '_'))}")

    # Portals often reuse one generic heading across every step.  A short
    # structural suffix keeps those steps distinct.  Pages with no step signal
    # at all keep the legacy identity (and the legacy file path).
    if parts:
        keys = sorted(_field_keys(form_map.get("fields") or []))
        if keys:
            digest = hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()[:8]
            parts.append(f"fields_{digest}")

    raw = "__".join(parts)
    if not raw:
        return ""
    safe = _safe_file_part(raw)
    if len(safe) > 100:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        safe = f"{safe[:91]}_{digest}"
    return safe


def _recipe_id_for(portal: str, page_type: str, page_key: str = "") -> str:
    base = f"{_safe_file_part(portal)}__{_safe_file_part(page_type)}"
    if page_key:
        base += f"__{_safe_file_part(page_key)}"
    return _bounded_id(base)


def _field_keys(fields: List[Dict[str, Any]]) -> set[str]:
    """Replayable keys only.

    Unknown placeholder keys and per-render human-challenge keys (which include
    an input index) are not stable identities, so they do not participate in
    step matching.
    """
    keys: set[str] = set()
    for field in fields:
        key = str(field.get("semantic_key") or field.get("key") or "").strip()
        if not key:
            continue
        if key.startswith("unknown_") or key.startswith("human_"):
            continue
        keys.add(key)
    return keys


class RecipeStore:
    """Local, human-inspectable recipe store.

    Recipes are per deployment by default.  Nothing in this class uploads a
    recipe or a field value anywhere.
    """

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or (settings.DATA_DIR / "recipes"))
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths

    def path_for(self, portal: str, page_type: str, page_key: str = "") -> Path:
        return self.root / f"{_recipe_id_for(portal, page_type, page_key)}.json"

    def _atomic_write(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    # ------------------------------------------------------------------ read

    def load(
        self, portal: str, page_type: str, page_key: str = ""
    ) -> Optional[Dict[str, Any]]:
        path = self.path_for(portal, page_type, page_key)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def load_by_id(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        recipe_id = _normalize_id(recipe_id)
        if not recipe_id:
            return None
        for path in self.root.glob("*.json"):
            if path.stem == recipe_id:
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    return None
        return None

    def list_recipes(self) -> List[Dict[str, Any]]:
        recipes: List[Dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                recipe = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            recipes.append(self.summary(recipe))
        recipes.sort(key=lambda item: item.get("last_seen_at") or "", reverse=True)
        return recipes

    @staticmethod
    def summary(recipe: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "recipe_id": recipe.get("recipe_id"),
            "portal": recipe.get("portal"),
            "page_type": recipe.get("page_type"),
            "page_key": recipe.get("page_key") or "",
            "step_heading": recipe.get("step_heading") or "",
            "fingerprint": recipe.get("fingerprint"),
            "fingerprint_short": str(recipe.get("fingerprint") or "")[:12],
            "version": recipe.get("version", 1),
            "status": recipe.get("status", "draft"),
            "source": recipe.get("source", "unknown"),
            "field_count": recipe.get("field_count", 0),
            "created_at": recipe.get("created_at"),
            "verified_at": recipe.get("verified_at"),
            "last_seen_at": recipe.get("last_seen_at"),
        }

    # ------------------------------------------------------------------ write

    def save_from_form_map(
        self,
        form_map: Dict[str, Any],
        *,
        source: str = "inspect",
        status: str = "draft",
    ) -> Dict[str, Any]:
        portal = str(form_map.get("portal") or "")
        page_type = str(form_map.get("page_type") or "unknown")
        page_key = page_key_for(form_map)
        previous = self._find_previous(portal, page_type, page_key, form_map)
        now = _utcnow()
        fields = FormModel.compact_for_recipe(form_map)

        version = 1
        created_at = now
        previous_fingerprint = None
        previous_page_key = ""
        recipe_id = _recipe_id_for(portal, page_type, page_key)
        target = self.path_for(portal, page_type, page_key)
        if previous:
            version = int(previous.get("version", 1))
            created_at = previous.get("created_at") or now
            previous_fingerprint = previous.get("fingerprint")
            previous_page_key = str(previous.get("page_key") or "")
            if previous_fingerprint != form_map.get("fingerprint"):
                version += 1
            # Keep the existing identity when a heading was renamed.  The
            # recipe is the same logical step with a new version, not a new
            # recipe.
            recipe_id = str(previous.get("recipe_id") or "") or recipe_id
            previous_path = self._path_for_recipe_id(recipe_id)
            if previous_path is not None:
                target = previous_path

        recipe = {
            "recipe_id": recipe_id,
            "portal": portal,
            "page_type": page_type,
            "page_key": page_key,
            "previous_page_key": (
                previous_page_key
                if previous_page_key and previous_page_key != page_key
                else None
            ),
            "step_heading": str(form_map.get("step_heading") or "")[:180],
            "active_section_id": str(form_map.get("active_section_id") or "")[:120],
            "form_action": str(form_map.get("form_action") or "")[:500],
            "url": form_map.get("display_url") or form_map.get("url"),
            "fingerprint": form_map.get("fingerprint"),
            "fingerprint_short": form_map.get("fingerprint_short"),
            "previous_fingerprint": previous_fingerprint,
            "version": version,
            "status": status,
            "source": source,
            "created_at": created_at,
            "verified_at": now if source == "inspect" else previous.get("verified_at") if previous else now,
            "last_seen_at": now,
            "field_count": len(fields),
            "fields": fields,
            "gateways": form_map.get("gateways") or [],
            "next_actions": form_map.get("next_actions") or [],
            "safety": {
                "human_handoff_only": ["captcha", "otp", "live_photo", "payment", "final_submission"],
                "never_auto_submit": True,
                "values_stored": False,
            },
        }
        self._atomic_write(target, recipe)
        return recipe

    # ------------------------------------------------------------------ matching

    def match(self, form_map: Dict[str, Any]) -> Dict[str, Any]:
        portal = str(form_map.get("portal") or "")
        page_type = str(form_map.get("page_type") or "unknown")
        page_key = page_key_for(form_map)
        fingerprint = str(form_map.get("fingerprint") or "")

        recipe = self.load(portal, page_type, page_key)
        if recipe is None:
            # A heading rename changes the derived key.  Fall back to a
            # structural search before calling this a new page.
            recipe = self._best_recipe(portal, form_map, page_type_only=True)
        if recipe is None:
            # A different page in a multi-step flow is normal.  Only a page
            # whose structure still resembles a saved recipe is drift.
            recipe = self._best_recipe(portal, form_map, page_type_only=False)
            if recipe is None:
                return {
                    "status": "new",
                    "confidence": 0,
                    "recipe_id": None,
                    "version": 0,
                    "drift": None,
                }

        if recipe.get("fingerprint") == fingerprint:
            return {
                "status": "match",
                "confidence": 100,
                "recipe_id": recipe.get("recipe_id"),
                "version": recipe.get("version", 1),
                "drift": None,
            }

        drift = self.diff(recipe.get("fields") or [], form_map.get("fields") or [])
        saved_page_key = str(recipe.get("page_key") or "")
        if recipe.get("page_type") != page_type:
            drift = {
                **drift,
                "page_type_changed": True,
                "summary": (
                    f"The portal is on a new page type: {page_type} instead of "
                    f"{recipe.get('page_type')}. "
                    + str(drift.get("summary") or "")
                ).strip(),
            }
        if saved_page_key and page_key and saved_page_key != page_key:
            drift = {**drift, "page_key_changed": True}
        return {
            "status": "drift",
            "confidence": 55,
            "recipe_id": recipe.get("recipe_id"),
            "version": recipe.get("version", 1),
            "page_key": page_key,
            "drift": drift,
        }

    def _portal_recipes(self, portal: str) -> List[Dict[str, Any]]:
        prefix = f"{_safe_file_part(portal)}__"
        recipes: List[Dict[str, Any]] = []
        for path in sorted(self.root.glob(f"{prefix}*.json")):
            try:
                recipes.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return recipes

    def _path_for_recipe_id(self, recipe_id: str) -> Optional[Path]:
        safe = _normalize_id(recipe_id)
        if not safe:
            return None
        for path in self.root.glob("*.json"):
            if path.stem == safe:
                return path
        return None

    @staticmethod
    def _score_recipe(recipe: Dict[str, Any], form_map: Dict[str, Any]) -> float:
        old_section = _norm_text(recipe.get("active_section_id"))
        new_section = _norm_text(form_map.get("active_section_id"))
        if old_section and new_section and old_section != new_section:
            return 0.0
        old_action = _action_path(recipe.get("form_action"))
        new_action = _action_path(form_map.get("form_action"))
        if old_action and new_action and old_action != new_action:
            return 0.0

        old_keys = _field_keys(recipe.get("fields") or [])
        new_keys = _field_keys(form_map.get("fields") or [])
        if not old_keys or not new_keys:
            return 0.0
        score = len(old_keys & new_keys) / len(old_keys | new_keys)

        if old_section and old_section == new_section:
            # The same active section with a different field set is a
            # redesign of that step, not a different step.
            score = max(score + 0.15, 0.8)
        old_heading = _norm_text(recipe.get("step_heading"))
        new_heading = _norm_text(form_map.get("step_heading"))
        if old_heading and old_heading == new_heading:
            score = min(1.0, score + 0.1)
        if old_action and old_action == new_action:
            score = min(1.0, score + 0.05)
        return score

    def _best_recipe(
        self,
        portal: str,
        form_map: Dict[str, Any],
        *,
        page_type_only: bool,
    ) -> Optional[Dict[str, Any]]:
        page_type = str(form_map.get("page_type") or "unknown")
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for recipe in self._portal_recipes(portal):
            if page_type_only and str(recipe.get("page_type") or "unknown") != page_type:
                continue
            score = self._score_recipe(recipe, form_map)
            if score > best_score:
                best = recipe
                best_score = score
        if best is not None and best_score >= _SIMILARITY_THRESHOLD:
            return best
        return None

    def _find_previous(
        self,
        portal: str,
        page_type: str,
        page_key: str,
        form_map: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        exact = self.load(portal, page_type, page_key)
        if exact is not None:
            return exact
        return self._best_recipe(portal, form_map, page_type_only=True)

    # ------------------------------------------------------------------ drift

    def diff(
        self,
        previous_fields: List[Dict[str, Any]],
        current_fields: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        previous = self._index_fields(previous_fields)
        current = self._index_fields(current_fields)
        added: List[Dict[str, Any]] = []
        removed: List[Dict[str, Any]] = []
        renamed: List[Dict[str, Any]] = []
        changed: List[Dict[str, Any]] = []
        matched_previous: set[str] = set()

        for key, old_field in previous.items():
            new_field = current.get(key)
            if new_field is not None:
                matched_previous.add(key)
                changes = self._compare_field(old_field, new_field)
                if changes:
                    changed.append(
                        {
                            "key": key,
                            "label": new_field.get("label"),
                            "changes": changes,
                        }
                    )
                continue

            candidate = self._find_renamed(old_field, current, matched_previous)
            if candidate:
                matched_previous.add(candidate[0])
                renamed.append(
                    {
                        "from": key,
                        "to": candidate[0],
                        "old_label": old_field.get("label"),
                        "new_label": candidate[1].get("label"),
                        "reason": "label_or_name_changed",
                    }
                )
            else:
                removed.append(
                    {
                        "key": key,
                        "label": old_field.get("label"),
                        "type": old_field.get("type"),
                    }
                )

        for key, field in current.items():
            if key in matched_previous or key in previous:
                continue
            added.append(
                {
                    "key": key,
                    "label": field.get("label"),
                    "type": field.get("type"),
                }
            )

        order_changed = False
        old_order = [key for key in previous]
        new_order = [key for key in current if key in previous]
        if old_order and new_order and old_order != new_order:
            order_changed = True

        structural = bool(removed or renamed or any(
            "type" in item.get("changes", []) for item in changed
        ))
        parts = []
        if added:
            parts.append(f"{len(added)} field(s) added")
        if removed:
            parts.append(f"{len(removed)} field(s) removed")
        if renamed:
            parts.append(f"{len(renamed)} field(s) renamed")
        if changed:
            parts.append(f"{len(changed)} field(s) changed")
        if order_changed:
            parts.append("field order changed")
        if not parts:
            parts.append("only cosmetic/structural noise changed")

        return {
            "summary": ", ".join(parts),
            "severity": "structural" if structural else "minor",
            "added": added[:20],
            "removed": removed[:20],
            "renamed": renamed[:20],
            "changed": changed[:20],
            "order_changed": order_changed,
            "requires_repair": structural,
            "requires_human_review": structural,
        }

    @staticmethod
    def _index_fields(fields: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        indexed: Dict[str, Dict[str, Any]] = {}
        for index, field in enumerate(fields):
            key = str(field.get("key") or field.get("semantic_key") or f"field_{index}")
            indexed[key] = field
        return indexed

    @staticmethod
    def _find_renamed(
        old_field: Dict[str, Any],
        current: Dict[str, Dict[str, Any]],
        already_matched: set[str],
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        old_label = _norm_text(old_field.get("label"))
        old_name = _norm_name(old_field.get("name"))
        for key, field in current.items():
            if key in already_matched:
                continue
            if old_label and old_label == _norm_text(field.get("label")):
                return key, field
            if old_name and old_name == _norm_name(field.get("name")):
                return key, field
        return None

    @staticmethod
    def _compare_field(old_field: Dict[str, Any], new_field: Dict[str, Any]) -> List[str]:
        changes: List[str] = []
        if _norm_text(old_field.get("label")) != _norm_text(new_field.get("label")):
            changes.append("label")
        if str(old_field.get("type") or "") != str(new_field.get("type") or ""):
            changes.append("type")
        if bool(old_field.get("required")) != bool(new_field.get("required")):
            changes.append("required")
        old_options = [str(option.get("text") or "") for option in old_field.get("options") or []]
        new_options = [str(option.get("text") or "") for option in new_field.get("options") or []]
        if old_options != new_options:
            changes.append("options")
        return changes


def fingerprint_signature(form_map: Dict[str, Any]) -> str:
    """Short stable signature used in events and traces."""
    raw = json.dumps(
        {
            "portal": form_map.get("portal"),
            "page_type": form_map.get("page_type"),
            "fingerprint": form_map.get("fingerprint"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
