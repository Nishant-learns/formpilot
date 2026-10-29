"""Turn a run journal into a plain-language report.

A log answers "what did the machine print?".  A report answers the two
questions a candidate actually has:

* what happened?
* what do I do now?

The report is built only from the persisted run journal (``meta.json``,
``steps.json``, ``events.jsonl`` and the masked ``audit.json``).  It never
reads the live page, the vault, or an unmasked value.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .failures import classify_failure, is_retryable


STATE_LABELS = {
    "IDLE": "Not started",
    "RESOLVING": "Opening the portal",
    "RUNNING": "In progress",
    "WAITING_FOR_USER": "Waiting for you",
    "PAUSED": "Paused",
    "AWAITING_PAYMENT": "Ready for your review",
    "INSPECT_READY": "Inspection complete",
    "DONE": "Finished",
    "COMPLETED": "Finished",
    "STOPPED": "Stopped",
    "FAILED": "Stopped with an error",
}

_KIND_LABELS = {
    "run": "Run",
    "perceive": "Read the page",
    "fill": "Filled fields",
    "advance": "Moved forward",
    "gate": "Checkpoint",
    "takeover": "Browser control",
    "submit": "Payment and final submission",
    "error": "Portal problem",
}

_TERMINAL = {"DONE", "COMPLETED", "STOPPED", "FAILED", "AWAITING_PAYMENT", "INSPECT_READY"}


def _output(step: Dict[str, Any]) -> Dict[str, Any]:
    output = step.get("output")
    return output if isinstance(output, dict) else {}


def _plural(count: int, singular: str, plural: Optional[str] = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _duration_text(milliseconds: Any) -> str:
    """Seconds for short steps, minutes and seconds for long ones, blank if unknown."""
    try:
        value = float(milliseconds)
    except (TypeError, ValueError):
        return ""
    if value < 1000:
        return ""
    seconds = int(round(value / 1000))
    if seconds < 90:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


_ACTION_LABELS = {
    "CONTINUE": "continued",
    "FILL_CONTINUE": "continued",
    "SECTION_APPROVAL": "section approved",
    "FILL_RECHECK": "asked to recheck and fill again",
    "RECHECK": "asked to recheck and fill again",
    "OTP_SUBMIT": "one-time code entered",
    "CAPTCHA_SUBMIT": "security check completed",
    "UPLOAD_COMPLETE": "document attached",
    "HANDOFF_COMPLETE": "browser step finished",
    "GATEWAY_CHOICE": "start path chosen",
    "LOGIN_METHOD_CHOICE": "sign-in method chosen",
    "ACCOUNT_IDENTIFIER_CHOICE": "account detail chosen",
    "ACCOUNT_CONFLICT": "existing account handled",
    "MISSING_FIELD_SUBMIT": "missing detail provided",
    "ACKNOWLEDGE_LOCK": "review acknowledged",
    "DISMISS": "checkpoint dismissed",
    "SKIP": "skipped",
}


def _action_label(action: Any) -> str:
    text = str(action or "").strip()
    if not text:
        return "answer received"
    return _ACTION_LABELS.get(text, text.replace("_", " ").lower())


def _last_step(steps: List[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    return next((step for step in reversed(steps) if step.get("kind") == kind), None)


def _step_detail(step: Dict[str, Any]) -> str:
    kind = str(step.get("kind") or "")
    status = str(step.get("status") or "")
    output = _output(step)
    if kind == "run":
        if output.get("state"):
            return f"Run ended in state {output['state']}."
        return "Run started."
    if kind == "perceive":
        page_type = output.get("page_type") or "page"
        fields = output.get("field_count")
        if fields is None:
            return f"Read the {page_type}."
        return f"Read the {page_type} with {_plural(int(fields), 'field')}."
    if kind == "fill":
        attempted = int(output.get("attempted") or 0)
        verified = int(output.get("verified") or 0)
        failed = int(output.get("failed") or 0)
        skipped = int(output.get("skipped") or 0)
        parts = [f"Verified {verified} of {_plural(attempted, 'field')}"]
        if failed:
            parts.append(f"{failed} failed")
        if skipped:
            parts.append(f"{skipped} skipped")
        if output.get("reformatted"):
            parts.append(f"{output['reformatted']} reformatted")
        if output.get("retried"):
            parts.append(f"{output['retried']} retried")
        return ", ".join(parts) + "."
    if kind == "advance":
        if status == "ok":
            return "Moved to the next step."
        return "The portal did not move to the next step."
    if kind == "gate":
        title = output.get("title") or output.get("gate_type") or "checkpoint"
        if status == "waiting":
            return f"Waiting for you: {title}."
        if status == "resolved":
            return f"Checkpoint resolved: {_action_label(output.get('action'))}."
        if status == "timed_out":
            return f"Checkpoint timed out: {title}."
        if status == "stopped":
            return f"Checkpoint stopped: {title}."
        return f"Checkpoint {status}: {title}."
    if kind == "takeover":
        event = output.get("event")
        if event == "started":
            return "You took control of the live browser."
        if event == "returned":
            return "You returned control; the page was re-read."
        return "Browser control changed."
    if kind == "submit":
        if status == "invalidated":
            reason = output.get("reason")
            if reason == "url_changed":
                return "The page address changed after your review; the review is no longer valid."
            return "A field changed after your review; the review is no longer valid."
        if output.get("final_action"):
            return "Stopped before the final submission. The last step is yours."
        return "Stopped before payment. The payment step is yours."
    if kind == "error":
        message = str(output.get("message") or "").strip()
        return message or "The portal reported a problem."
    return status or "Step recorded."


def _step_label(step: Dict[str, Any]) -> str:
    return _KIND_LABELS.get(str(step.get("kind") or ""), str(step.get("kind") or "Step"))


def _timeline(steps: List[Dict[str, Any]], run_id: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for step in steps:
        seq = step.get("seq")
        items.append(
            {
                "seq": seq,
                "at": step.get("started_at"),
                "kind": step.get("kind"),
                "label": _step_label(step),
                "detail": _step_detail(step),
                "status": step.get("status"),
                "duration_ms": step.get("duration_ms"),
                "error_code": step.get("error_code"),
                "retryable": bool(step.get("retryable")),
                "page_signature": step.get("page_signature") or "",
                "anchor": f"#step-{seq}" if seq else "",
                "raw": f"/api/runs/{run_id}/steps",
            }
        )
    return items


_PHASE_LABELS = {
    "SENSE": "Read the page",
    "THINK": "Thought about the page",
    "ACT": "Took an action",
    "DECIDE": "Stopped for you",
    "INSPECT": "Inspected the page",
}


def _event_timeline(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A readable timeline for runs recorded before the step ledger existed."""
    items: List[Dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        phase = str(event.get("phase") or "")
        message = str(event.get("message") or "").strip()
        if not message:
            continue
        items.append(
            {
                "seq": index,
                "at": event.get("timestamp"),
                "kind": "event",
                "label": _PHASE_LABELS.get(phase, phase.title() or "Event"),
                "detail": message,
                "status": "",
                "duration_ms": None,
                "error_code": "",
                "retryable": False,
                "page_signature": "",
                "anchor": f"#step-{index}",
                "raw": "",
            }
        )
    return items


def _stats(steps: List[Dict[str, Any]], meta: Dict[str, Any]) -> Dict[str, Any]:
    fill_steps = [step for step in steps if step.get("kind") == "fill"]
    gate_steps = [step for step in steps if step.get("kind") == "gate"]
    clock = meta.get("run_clock") if isinstance(meta.get("run_clock"), dict) else {}
    usage = meta.get("llm_usage") if isinstance(meta.get("llm_usage"), dict) else {}
    return {
        "steps": len(steps),
        "pages_read": sum(1 for step in steps if step.get("kind") == "perceive"),
        "fields_attempted": sum(int(_output(step).get("attempted") or 0) for step in fill_steps),
        "fields_verified": sum(int(_output(step).get("verified") or 0) for step in fill_steps),
        "fields_failed": sum(int(_output(step).get("failed") or 0) for step in fill_steps),
        "fields_skipped": sum(int(_output(step).get("skipped") or 0) for step in fill_steps),
        "retried": sum(1 for step in steps if int(step.get("attempt") or 1) > 1),
        "gates": len(gate_steps),
        "gates_waiting": sum(1 for step in gate_steps if step.get("status") == "waiting"),
        "gates_resolved": sum(1 for step in gate_steps if step.get("status") == "resolved"),
        "takeovers": sum(1 for step in steps if step.get("kind") == "takeover"),
        "errors": sum(1 for step in steps if step.get("kind") == "error"),
        "duration_ms": meta.get("duration_ms"),
        "active_seconds": clock.get("active_seconds"),
        "attended_seconds": clock.get("attended_seconds"),
        "wall_seconds": clock.get("wall_seconds"),
        "model_calls": usage.get("calls"),
        "model_errors": usage.get("errors"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "estimated_cost_usd": usage.get("estimated_cost_usd"),
    }


def _failure(steps: List[Dict[str, Any]], meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    message = str(meta.get("error") or "").strip()
    code = str(meta.get("error_code") or "").strip()
    step = next(
        (item for item in reversed(steps) if item.get("error_code") or item.get("kind") == "error"),
        None,
    )
    if not message and step:
        message = str(_output(step).get("message") or "").strip()
    if not code and step:
        code = str(step.get("error_code") or "").strip()
    if not code and message:
        code = classify_failure(message).value
    if not code and not message:
        return None
    retryable = bool(step.get("retryable")) if step else is_retryable(code)
    return {
        "code": code or classify_failure(message).value,
        "retryable": retryable,
        "message": message or "The run stopped before it could finish.",
    }


def _what_happened(
    steps: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    stats: Dict[str, Any],
    failure: Optional[Dict[str, Any]],
) -> List[str]:
    lines: List[str] = []
    if stats["pages_read"]:
        lines.append(f"FormPilot read the page {_plural(stats['pages_read'], 'time')}.")
    if stats["fields_attempted"]:
        lines.append(
            f"It tried {_plural(stats['fields_attempted'], 'field')}; the portal kept "
            f"{stats['fields_verified']} of {stats['fields_attempted']}."
        )
    if stats["gates"]:
        lines.append(
            f"There {'was' if stats['gates'] == 1 else 'were'} "
            f"{_plural(stats['gates'], 'checkpoint')}: "
            f"{stats['gates_resolved']} resolved, {stats['gates_waiting']} still waiting."
        )
    if stats["takeovers"]:
        lines.append("You took control of the live browser at least once.")
    if stats["retried"]:
        lines.append(f"{_plural(stats['retried'], 'field')} needed a second attempt.")
    if stats.get("model_calls"):
        line = f"The model was called {_plural(stats['model_calls'], 'time')}"
        if stats.get("total_tokens"):
            line += f" and used {stats['total_tokens']:,} tokens"
        if stats.get("estimated_cost_usd"):
            line += f" (about ${stats['estimated_cost_usd']:.4f})"
        lines.append(line + ".")
    if failure:
        lines.append(
            f"The last problem was classified as {failure['code']}"
            + (" (retryable)." if failure["retryable"] else " (not retryable).")
        )
    for event in events[-3:]:
        message = str(event.get("message") or "").strip()
        if message and message not in lines:
            lines.append(message)
    if not lines:
        lines.append("This run did not record any steps yet.")
    return lines[:8]


def _what_to_do_now(
    state: str,
    steps: List[Dict[str, Any]],
    meta: Dict[str, Any],
    failure: Optional[Dict[str, Any]],
    events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    if state == "AWAITING_PAYMENT":
        submit = _last_step(steps, "submit")
        output = _output(submit or {})
        if submit and submit.get("status") == "invalidated":
            return {
                "kind": "human",
                "title": "Review the form again",
                "detail": (
                    "The page changed after your review. Check the form again, then "
                    "complete the payment or final submission yourself."
                ),
            }
        if output.get("final_action"):
            return {
                "kind": "human",
                "title": "Complete the final submission yourself",
                "detail": (
                    "FormPilot stopped before submitting anything. Open the portal and "
                    "complete the final submission yourself."
                ),
            }
        return {
            "kind": "human",
            "title": "Complete the payment yourself",
            "detail": (
                "FormPilot stopped before any payment action. Open the portal and "
                "complete the payment yourself."
            ),
        }
    if state == "WAITING_FOR_USER":
        gate = next(
            (step for step in reversed(steps) if step.get("kind") == "gate" and step.get("status") == "waiting"),
            None,
        )
        title = _output(gate or {}).get("title") if gate else ""
        if not title:
            # Older runs have no gate row; the last gate event still says why.
            gate_events = [
                item
                for item in (events or [])
                if item.get("gate_type") and item.get("message")
            ]
            waiting = [
                item
                for item in gate_events
                if str(item.get("message") or "").strip().lower().startswith("waiting")
            ]
            event = (waiting or gate_events or [None])[-1]
            title = str((event or {}).get("message") or "").strip()
        if title:
            title = title.rstrip(".")
        return {
            "kind": "human",
            "title": "Answer the checkpoint",
            "detail": (
                f"Open the cockpit and answer: {title}."
                if title
                else "Open the cockpit and answer the waiting checkpoint."
            ),
        }
    if state == "PAUSED":
        return {
            "kind": "human",
            "title": "Continue when you are ready",
            "detail": "Open the live browser, make any changes you need, then press Continue.",
        }
    if state == "FAILED":
        detail = "Read the error below, then try again or continue in the official portal."
        if failure and failure.get("retryable"):
            detail = "The problem looks temporary. Try again; if it repeats, continue in the official portal."
        return {"kind": "error", "title": "The run stopped", "detail": detail}
    if state in {"DONE", "COMPLETED"}:
        return {
            "kind": "info",
            "title": "Nothing is pending",
            "detail": "The run finished. If the portal still needs a submission or payment, do it yourself.",
        }
    if state == "STOPPED":
        return {
            "kind": "info",
            "title": "The run was stopped",
            "detail": "Start a new application when you are ready, or continue directly in the portal.",
        }
    if state == "INSPECT_READY":
        return {
            "kind": "info",
            "title": "Inspection complete",
            "detail": "Review the page map. Nothing was submitted.",
        }
    if state in {"RUNNING", "RESOLVING"}:
        return {
            "kind": "info",
            "title": "The run is in progress",
            "detail": "Watch the cockpit. No action is needed right now.",
        }
    return {
        "kind": "info",
        "title": "Start an application",
        "detail": "Open the cockpit and start a new application when you are ready.",
    }


def build_run_report(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Build the plain-language report for one run."""
    meta = detail.get("meta") or {}
    steps = detail.get("steps") or []
    events = detail.get("events") or []
    audit = detail.get("audit") or None
    state = str(meta.get("state") or "UNKNOWN")
    stats = _stats(steps, meta)
    failure = _failure(steps, meta)
    audit_stats = None
    if isinstance(audit, dict):
        audit_stats = {
            "checked": audit.get("total_checked"),
            "matched": audit.get("total_matched"),
            "mismatches": audit.get("total_mismatches"),
            "values_masked": bool(audit.get("values_masked")),
            "audit_hash": audit.get("audit_hash"),
        }
    headline = f"{STATE_LABELS.get(state, state)}"
    if stats["fields_attempted"]:
        headline += (
            f" · {stats['fields_verified']} of {stats['fields_attempted']} fields verified"
        )
    headline_duration = _duration_text(stats["duration_ms"])
    if headline_duration:
        headline += f" · {headline_duration}"
    run_id = str(meta.get("run_id") or detail.get("run_id") or "")
    return {
        "run_id": run_id,
        "state": state,
        "state_label": STATE_LABELS.get(state, state),
        "headline": headline,
        "what_happened": _what_happened(steps, events, stats, failure),
        "what_to_do_now": _what_to_do_now(state, steps, meta, failure, events),
        "failure": failure,
        "stats": stats,
        "audit": audit_stats,
        "timeline": _timeline(steps, run_id) or _event_timeline(events),
        "links": {
            "run": f"/runs/{run_id}",
            "json": f"/api/runs/{run_id}",
            "steps": f"/api/runs/{run_id}/steps",
            "audit": f"/api/runs/{run_id}/audit",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def render_run_report_html(report: Dict[str, Any]) -> str:
    """A dependency-free, printable run page for a non-engineer."""
    state = report.get("state") or "UNKNOWN"
    action = report.get("what_to_do_now") or {}
    tone = {
        "human": "#f59e0b",
        "error": "#ef4444",
        "info": "#38bdf8",
    }.get(str(action.get("kind") or "info"), "#38bdf8")
    happened = "".join(f"<li>{_e(line)}</li>" for line in report.get("what_happened") or [])
    stats = report.get("stats") or {}
    audit = report.get("audit") or {}
    failure = report.get("failure") or {}
    timeline_rows = []
    for item in report.get("timeline") or []:
        duration_text = _duration_text(item.get("duration_ms")) or "—"
        error = item.get("error_code") or ""
        timeline_rows.append(
            "<tr id=\"step-{seq}\">"
            "<td class=\"mono\">{seq}</td>"
            "<td><strong>{label}</strong><div class=\"muted\">{detail}</div></td>"
            "<td class=\"mono\">{status}</td>"
            "<td class=\"mono\">{duration}</td>"
            "<td class=\"mono\">{error}</td>"
            "</tr>".format(
                seq=_e(item.get("seq")),
                label=_e(item.get("label")),
                detail=_e(item.get("detail")),
                status=_e(item.get("status")),
                duration=_e(duration_text),
                error=_e(error),
            )
        )
    failure_html = ""
    if failure:
        failure_html = f"""
        <section class="card failure">
          <h2>Last problem</h2>
          <p><strong>{_e(failure.get('code'))}</strong> · {_e(failure.get('message'))}</p>
          <p class="muted">{'A retry may work.' if failure.get('retryable') else 'A retry alone will not fix this.'}</p>
        </section>"""
    audit_html = ""
    if audit:
        audit_html = f"""
        <section class="card">
          <h2>Pre-payment audit</h2>
          <p>{_e(audit.get('matched'))} of {_e(audit.get('checked'))} fields matched.
          {_e(audit.get('mismatches'))} needed review.
          {'Values are masked in the saved file.' if audit.get('values_masked') else ''}</p>
          <p class="muted mono">hash {_e(audit.get('audit_hash'))}</p>
        </section>"""
    links = report.get("links") or {}
    if int(stats.get("steps") or 0) or int(stats.get("pages_read") or 0):
        cards = [
            (f"{stats.get('fields_verified') or 0}/{stats.get('fields_attempted') or 0}", "fields verified"),
            (stats.get("gates") or 0, "checkpoints"),
            (stats.get("retried") or 0, "retries"),
            (stats.get("errors") or 0, "portal errors"),
        ]
        if stats.get("active_seconds") is not None:
            cards.append((f"{stats['active_seconds']}s", "active work"))
        if stats.get("attended_seconds") is not None:
            cards.append((f"{stats['attended_seconds']}s", "with you"))
        if stats.get("model_calls") is not None:
            cards.append((stats["model_calls"], "model calls"))
        if stats.get("total_tokens"):
            cards.append((f"{int(stats['total_tokens']):,}", "tokens"))
        card_html = "".join(
            f'      <div class="stat"><b>{_e(value)}</b>{_e(label)}</div>\n'
            for value, label in cards
        )
        stats_html = (
            '<section class="card">\n'
            "    <h2>At a glance</h2>\n"
            '    <div class="grid">\n'
            f"{card_html}"
            "    </div>\n"
            "  </section>"
        )
    else:
        stats_html = (
            '<section class="card">\n'
            "    <h2>At a glance</h2>\n"
            '    <p class="muted">This run was recorded before the step ledger, so only '
            "its event timeline is available.</p>\n"
            "  </section>"
        )
    audit_link = (
        f'<a href="{_e(links.get("audit"))}">Download the audit JSON</a> · '
        if audit
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FormPilot run report · {_e(report.get('run_id'))}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; padding: 32px 20px; background: #0f172a; color: #e2e8f0;
         font: 15px/1.55 system-ui, -apple-system, Segoe UI, sans-serif; }}
  main {{ max-width: 920px; margin: 0 auto; }}
  h1 {{ margin: 0 0 6px; font-size: 26px; }}
  h2 {{ margin: 0 0 8px; font-size: 16px; color: #cbd5e1; }}
  .muted {{ color: #94a3b8; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
  .badge {{ display: inline-block; padding: 3px 9px; border-radius: 999px;
            background: #1e293b; border: 1px solid #334155; font-size: 12px; }}
  .card {{ background: #111c31; border: 1px solid #24344d; border-radius: 14px;
           padding: 18px 20px; margin: 16px 0; }}
  .action {{ border-left: 5px solid {tone}; }}
  .failure {{ border-left: 5px solid #ef4444; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
           gap: 12px; }}
  .stat {{ background: #0b1526; border: 1px solid #24344d; border-radius: 10px;
           padding: 10px 12px; }}
  .stat b {{ display: block; font-size: 20px; color: #f8fafc; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 9px 8px; border-bottom: 1px solid #1f2f47;
            vertical-align: top; }}
  th {{ color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }}
  a {{ color: #7dd3fc; }}
  footer {{ margin-top: 26px; color: #94a3b8; font-size: 12px; }}
</style>
</head>
<body>
<main>
  <span class="badge">{_e(report.get('state_label'))}</span>
  <h1>{_e(report.get('headline'))}</h1>
  <p class="muted mono">run {_e(report.get('run_id'))} · generated {_e(report.get('generated_at'))}</p>

  <section class="card action">
    <h2>{_e(action.get('title'))}</h2>
    <p>{_e(action.get('detail'))}</p>
  </section>

  <section class="card">
    <h2>What happened</h2>
    <ul>{happened}</ul>
  </section>

  {stats_html}

  {failure_html}
  {audit_html}

  <section class="card">
    <h2>Timeline</h2>
    <table>
      <thead><tr><th>#</th><th>Step</th><th>Status</th><th>Time</th><th>Code</th></tr></thead>
      <tbody>{''.join(timeline_rows) or '<tr><td colspan="5" class="muted">No steps recorded.</td></tr>'}</tbody>
    </table>
  </section>

  <p>{audit_link}<a href="{_e(links.get('json'))}">Open the raw run journal</a></p>
  <footer>FormPilot never solves a CAPTCHA, enters an OTP, pays, or submits on your behalf.
  This report is built from the recorded run and contains masked values.</footer>
</main>
</body>
</html>"""
