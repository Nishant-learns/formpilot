"""A small operator CLI for FormPilot.

Two kinds of commands:

* **Local reads** — ``runs``, ``show`` and ``report`` read the run journal from
  disk.  They work with the server stopped and never touch the live page.
* **Cockpit control** — ``status``, ``start``, ``follow``, ``answer`` and
  ``stop`` talk to the local API at ``FORMPILOT_BASE_URL`` (default
  ``http://127.0.0.1:8000``).

The CLI never answers a human-only gate.  A one-time code, a CAPTCHA, a live
photo, a payment or the final submission stays in the cockpit or the browser:
the terminal is a convenient client, not a way around the human boundary.

Usage::

    python -m backend.cli status
    python -m backend.cli runs --limit 10
    python -m backend.cli show run-20261029-101500-a1b2c3
    python -m backend.cli report run-... --out report.html
    python -m backend.cli start https://portal.example/apply --follow
    python -m backend.cli answer CONTINUE
    python -m backend.cli stop
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .core.run_report import build_run_report, render_run_report_html
from .core.run_store import RunStore

DEFAULT_BASE_URL = os.getenv("FORMPILOT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# Actions a terminal may send.  Everything else belongs to the cockpit or the
# browser, where the human can see the page while acting.
SAFE_ACTIONS = {
    "CONTINUE",
    "FILL_CONTINUE",
    "FILL_RECHECK",
    "RECHECK",
    "SECTION_APPROVAL",
    "DISMISS",
    "STOPPED",
}

HUMAN_ONLY_REASONS = {
    "otp_human_only",
    "captcha_human_only",
    "live_photo",
    "pre_payment_review",
    "file_upload",
    "human_handoff",
}

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CHECKPOINT = 3
EXIT_SERVER = 4


# --------------------------------------------------------------------- output


def _print(text: str = "") -> None:
    sys.stdout.write(text + "\n")


def _fail(message: str, code: int = EXIT_USAGE) -> int:
    sys.stderr.write(message.rstrip() + "\n")
    return code


# ------------------------------------------------------------------------ API


class ApiError(RuntimeError):
    pass


def _request(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 15.0,
) -> Any:
    url = f"{base_url}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ApiError(f"{method} {path} returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(
            f"Cannot reach the cockpit at {base_url}. Is the server running?"
        ) from exc
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _clock_text(clock: Dict[str, Any]) -> str:
    if not clock or not clock.get("started_at"):
        return "not started"
    active = int(clock.get("active_seconds") or 0)
    attended = int(clock.get("attended_seconds") or 0)
    text = f"{active}s active, {attended}s with you"
    if clock.get("gate_open"):
        text += ", checkpoint open"
    return text


def _gate_text(gate: Dict[str, Any]) -> str:
    lines = [
        f"Checkpoint: {gate.get('title') or gate.get('gate_type') or 'review'}",
    ]
    if gate.get("reason"):
        lines.append(f"  reason: {gate['reason']}")
    if gate.get("description"):
        lines.append(f"  {gate['description']}")
    recommended = gate.get("recommended") or {}
    if recommended.get("label"):
        lines.append(f"  suggested first step: {recommended['label']}")
    options = gate.get("options") or []
    for index, option in enumerate(options, start=1):
        label = option.get("label") or option.get("text") or option.get("value")
        action = option.get("action") or option.get("mode") or ""
        suffix = f" [{action}]" if action else ""
        lines.append(f"  {index}. {label}{suffix}")
    if gate.get("reason") in HUMAN_ONLY_REASONS:
        lines.append(
            "  This step is yours: finish it in the cockpit or the live browser."
        )
    return "\n".join(lines)


# ------------------------------------------------------------------- commands


def cmd_status(args: argparse.Namespace) -> int:
    try:
        state = _request("GET", "/api/agent/state", base_url=args.base_url)
    except ApiError as exc:
        return _fail(str(exc), EXIT_SERVER)
    gate = state.get("active_gate") or {}
    _print(f"state:  {state.get('state')}")
    _print(f"run:    {state.get('run_id') or '-'}")
    _print(f"mode:   {state.get('run_mode') or state.get('mode') or '-'}")
    _print(f"url:    {state.get('target_url') or '-'}")
    _print(f"clock:  {_clock_text(state.get('run_clock') or {})}")
    usage = state.get("llm_usage") or {}
    if usage.get("calls"):
        _print(f"model:  {usage['calls']} call(s), {usage.get('total_tokens') or 0} token(s)")
    if gate:
        _print("")
        _print(_gate_text(gate))
    return EXIT_OK


def cmd_runs(args: argparse.Namespace) -> int:
    store = RunStore(args.runs_dir) if args.runs_dir else RunStore()
    try:
        page = store.list_runs_page(limit=args.limit, cursor=args.cursor)
    except ValueError as exc:
        return _fail(str(exc))
    runs: List[Dict[str, Any]] = page.get("runs") or []
    if not runs:
        _print("No runs recorded yet.")
        return EXIT_OK
    _print(f"{'run':38} {'state':18} {'steps':>5}  started")
    for run in runs:
        _print(
            f"{str(run.get('run_id')):38} {str(run.get('state')):18} "
            f"{int(run.get('steps') or 0):5}  {run.get('started_at') or '-'}"
        )
    if page.get("next_cursor"):
        _print("")
        _print(f"next page: --cursor {page['next_cursor']}")
    return EXIT_OK


def _load_report(args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    store = RunStore(args.runs_dir) if args.runs_dir else RunStore()
    detail = store.run_detail(args.run_id)
    if not detail:
        return None
    return build_run_report(detail)


def cmd_show(args: argparse.Namespace) -> int:
    report = _load_report(args)
    if report is None:
        return _fail(f"Run not found: {args.run_id}")
    if args.json:
        _print(json.dumps(report, indent=2, ensure_ascii=False))
        return EXIT_OK
    _print(report.get("headline") or report.get("state_label") or "")
    _print(f"run {report.get('run_id')} · {report.get('generated_at')}")
    _print("")
    action = report.get("what_to_do_now") or {}
    _print(f"DO THIS NOW: {action.get('title')}")
    if action.get("detail"):
        _print(f"  {action['detail']}")
    _print("")
    _print("What happened:")
    for line in report.get("what_happened") or []:
        _print(f"  - {line}")
    failure = report.get("failure") or {}
    if failure:
        _print("")
        _print(f"Last problem: {failure.get('code')} · {failure.get('message')}")
        _print(
            "  A retry may work."
            if failure.get("retryable")
            else "  A retry alone will not fix this."
        )
    stats = report.get("stats") or {}
    if stats.get("steps"):
        _print("")
        _print(
            f"fields {stats.get('fields_verified')}/{stats.get('fields_attempted')} · "
            f"checkpoints {stats.get('gates')} · retries {stats.get('retried')} · "
            f"errors {stats.get('errors')}"
        )
        if stats.get("model_calls") is not None:
            _print(
                f"model calls {stats.get('model_calls')} · "
                f"tokens {stats.get('total_tokens') or 0}"
            )
    if args.timeline:
        _print("")
        _print("Timeline:")
        for item in report.get("timeline") or []:
            _print(f"  {item.get('seq'):>3}  {item.get('label')}: {item.get('detail')}")
    _print("")
    _print(f"page: {args.base_url}/runs/{report.get('run_id')}")
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    report = _load_report(args)
    if report is None:
        return _fail(f"Run not found: {args.run_id}")
    page = render_run_report_html(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(page)
        _print(f"Wrote {args.out}")
    else:
        sys.stdout.write(page)
    return EXIT_OK


def _follow(args: argparse.Namespace, *, run_id: str) -> int:
    """Print new events until the run stops or a checkpoint opens."""
    seen: set = set()
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            detail = _request(
                "GET", f"/api/runs/{run_id}", base_url=args.base_url
            )
            state = _request("GET", "/api/agent/state", base_url=args.base_url)
        except ApiError as exc:
            return _fail(str(exc), EXIT_SERVER)
        for event in (detail or {}).get("events") or []:
            key = (event.get("timestamp"), event.get("message"))
            if key in seen:
                continue
            seen.add(key)
            stamp = event.get("timestamp") or ""
            _print(f"{stamp}  {event.get('phase') or '':8}  {event.get('message') or ''}")
        gate = state.get("active_gate") or {}
        if gate:
            _print("")
            _print(_gate_text(gate))
            return EXIT_CHECKPOINT
        current = str(state.get("state") or "")
        if current in {"DONE", "FAILED", "STOPPED", "AWAITING_PAYMENT", "INSPECT_READY"}:
            _print("")
            _print(f"Run {run_id} is {current}.")
            _print(f"page: {args.base_url}/runs/{run_id}")
            return EXIT_OK
        time.sleep(args.interval)
    _print("Stopped following; the run is still in progress.")
    return EXIT_OK


def cmd_start(args: argparse.Namespace) -> int:
    try:
        response = _request(
            "POST",
            "/api/agent/start",
            {"query_or_url": args.query_or_url, "mode": args.mode},
            base_url=args.base_url,
        )
    except ApiError as exc:
        return _fail(str(exc), EXIT_SERVER)
    if not response or not response.get("success"):
        return _fail(str((response or {}).get("message") or "The run did not start."))
    run_id = str(response.get("run_id") or "")
    _print(f"Started run {run_id} ({response.get('mode')}).")
    if args.follow:
        time.sleep(args.interval)
        return _follow(args, run_id=run_id)
    _print("Follow it with: python -m backend.cli follow")
    return EXIT_OK


def cmd_follow(args: argparse.Namespace) -> int:
    try:
        state = _request("GET", "/api/agent/state", base_url=args.base_url)
    except ApiError as exc:
        return _fail(str(exc), EXIT_SERVER)
    run_id = str(state.get("run_id") or "")
    if not run_id:
        return _fail("There is no active run to follow.")
    return _follow(args, run_id=run_id)


def cmd_answer(args: argparse.Namespace) -> int:
    action = str(args.action or "").upper()
    if action not in SAFE_ACTIONS:
        return _fail(
            f"'{action}' is not a terminal action. Finish this step in the cockpit "
            "or the live browser."
        )
    payload: Dict[str, Any] = {"action": action}
    if args.option:
        payload["value"] = args.option
        payload["text"] = args.option
    try:
        response = _request(
            "POST", "/api/agent/user-response", payload, base_url=args.base_url
        )
    except ApiError as exc:
        return _fail(str(exc), EXIT_SERVER)
    if response and response.get("success") is False:
        return _fail(str(response.get("message") or "The answer was not accepted."))
    _print(f"Sent {action}.")
    return EXIT_OK


def cmd_stop(args: argparse.Namespace) -> int:
    try:
        _request("POST", "/api/agent/stop", {}, base_url=args.base_url)
    except ApiError as exc:
        return _fail(str(exc), EXIT_SERVER)
    _print("Stop requested.")
    return EXIT_OK


# ---------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="formpilot",
        description="Operator CLI for FormPilot. Reads run journals and drives the cockpit.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Cockpit URL for control commands (default: %(default)s).",
    )
    parser.add_argument(
        "--runs-dir",
        default="",
        help="Run journal directory for local reads (default: the app data dir).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show the cockpit state and any open checkpoint.")
    status.set_defaults(func=cmd_status)

    runs = sub.add_parser("runs", help="List recorded runs.")
    runs.add_argument("--limit", type=int, default=20)
    runs.add_argument("--cursor", default=None, help="Cursor from a previous page.")
    runs.set_defaults(func=cmd_runs)

    show = sub.add_parser("show", help="Print the plain-language report for a run.")
    show.add_argument("run_id")
    show.add_argument("--json", action="store_true", help="Print the report as JSON.")
    show.add_argument("--timeline", action="store_true", help="Include every step.")
    show.set_defaults(func=cmd_show)

    report = sub.add_parser("report", help="Write the printable HTML report.")
    report.add_argument("run_id")
    report.add_argument("--out", default="", help="Write to this file instead of stdout.")
    report.set_defaults(func=cmd_report)

    start = sub.add_parser("start", help="Start a run through the local cockpit.")
    start.add_argument("query_or_url")
    start.add_argument("--mode", choices=["fill", "inspect"], default="fill")
    start.add_argument("--follow", action="store_true", help="Print events until a checkpoint.")
    start.add_argument("--interval", type=float, default=1.0)
    start.add_argument("--timeout", type=float, default=900.0)
    start.set_defaults(func=cmd_start)

    follow = sub.add_parser("follow", help="Print events for the active run.")
    follow.add_argument("--interval", type=float, default=1.0)
    follow.add_argument("--timeout", type=float, default=900.0)
    follow.set_defaults(func=cmd_follow)

    answer = sub.add_parser(
        "answer",
        help="Send a safe action (continue, recheck, dismiss) to an open checkpoint.",
    )
    answer.add_argument("action")
    answer.add_argument("--option", default="", help="Option value for a choice action.")
    answer.set_defaults(func=cmd_answer)

    stop = sub.add_parser("stop", help="Stop the active run.")
    stop.set_defaults(func=cmd_stop)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
