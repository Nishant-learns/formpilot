from __future__ import annotations

import asyncio
import datetime
import hmac
import json
import os
import re
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .core import field_registry, settings
from .core.biometrics import BiometricCompressor
from .core.chat_assistant import FormPilotChatAssistant
from .core.live_browser import live_sessions
from .core.oracle import PortalOracle
from .core.orchestrator import AgentRunError, FormPilotOrchestrator
from .core.recipe import RecipeStore
from .core.run_store import RunStore
from .core.tinyfish_client import EngineConfig, TinyFishClient, TinyFishError
from .core.vault import CandidateVault, VaultManager

if settings.ENABLE_SIMULATOR:
    from .simulator.portal import router as simulator_router
else:  # pragma: no cover - production deployments can disable the practice portal
    simulator_router = None


settings.ensure_directories()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_directories()
    yield
    try:
        if orchestrator.is_running or orchestrator.browser or orchestrator.page:
            await orchestrator.stop()
        elif orchestrator._session and orchestrator._session.is_cloud:
            await orchestrator.tinyfish_mgr.terminate_session(orchestrator._session.session_id)
    except Exception:
        traceback.print_exc()


app = FastAPI(
    title="FormPilot API",
    version=settings.APP_VERSION,
    description="Guided form-filling assistant for public recruitment and admission portals.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Token", "X-Request-ID"],
)

if simulator_router is not None:
    app.include_router(simulator_router)

vault_mgr = VaultManager.get_instance()
tinyfish_client = TinyFishClient()
run_store = RunStore()
active_connections: List[WebSocket] = []


async def broadcast_to_cockpits(event: Dict[str, Any]):
    disconnected: List[WebSocket] = []
    for websocket in list(active_connections):
        try:
            await websocket.send_json(event)
        except Exception:
            disconnected.append(websocket)
    for websocket in disconnected:
        if websocket in active_connections:
            active_connections.remove(websocket)


orchestrator = FormPilotOrchestrator(broadcast_fn=broadcast_to_cockpits)
chat_assistant = FormPilotChatAssistant(orchestrator=orchestrator)


# --------------------------------------------------------------------------- security


def _request_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (
        request.headers.get("x-api-token")
        or request.query_params.get("token")
        or ""
    )


def _safe_compare(candidate: str) -> bool:
    return bool(candidate) and hmac.compare_digest(candidate, settings.AUTH_TOKEN)


@app.middleware("http")
async def security_headers_and_auth(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id

    path = request.url.path
    protected = (
        path.startswith("/api/")
        and not path.startswith("/api/health")
        and not path.startswith("/api/portal/")
    ) or path.startswith("/uploads/")
    if settings.AUTH_REQUIRED and protected:
        if not _safe_compare(_request_token(request)):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required."},
                headers={"X-Request-ID": request_id},
            )

    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    # The live-photo checkpoint runs in this page, so the camera must be
    # allowed for the same origin. Microphone and geolocation stay off.
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
    if path.startswith("/api/vault") or path.startswith("/uploads/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong. Please try again."},
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


# --------------------------------------------------------------------------- vault


@app.get("/api/vault")
def get_vault(masked: bool = Query(False)):
    data = vault_mgr.vault.public_dict(mask_sensitive=masked or settings.MASK_PII)
    return JSONResponse(content=data, headers={"Cache-Control": "no-store"})


@app.post("/api/vault")
def update_vault(data: Dict[str, Any]):
    if len(json.dumps(data)) > 250_000:
        raise HTTPException(status_code=413, detail="Vault payload is too large.")
    try:
        updated = vault_mgr.update(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid vault data: {exc}") from exc
    return {"success": True, "vault": updated.public_dict(mask_sensitive=settings.MASK_PII)}


@app.post("/api/vault/custom-field")
def add_custom_field(field_name: str = Form(...), field_value: str = Form(...)):
    if len(field_name) > 80 or len(field_value) > 500:
        raise HTTPException(status_code=413, detail="Field is too large.")
    updated = vault_mgr.add_custom_field(field_name, field_value)
    return {"success": True, "vault": updated.public_dict(mask_sensitive=settings.MASK_PII)}


@app.post("/api/vault/reset")
def reset_vault():
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Vault reset is only available in demo mode.")
    default_vault = vault_mgr.reset_defaults()
    return {"success": True, "vault": default_vault.public_dict(mask_sensitive=settings.MASK_PII)}


# --------------------------------------------------------------------------- oracle


@app.get("/api/oracle/search")
async def oracle_search(
    q: str = Query(..., min_length=2, max_length=400),
    live: bool = Query(True),
):
    if live:
        result = await PortalOracle.resolve_target_live(q, tinyfish_client)
    else:
        result = PortalOracle.resolve_target(q)
    return result.model_dump()


@app.get("/api/oracle/directory")
def get_verified_directory():
    return PortalOracle.directory()


# --------------------------------------------------------------------------- biometrics


MAX_UPLOAD_BYTES = 12 * 1024 * 1024


async def _read_upload(file: UploadFile) -> bytes:
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large. Maximum size is 12 MB.")
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Please upload an image file.")
    return contents


@app.post("/api/biometrics/compress-photo")
async def compress_photo(
    file: UploadFile = File(...),
    target_width: int = Form(350),
    target_height: int = Form(350),
    min_kb: float = Form(20.0),
    max_kb: float = Form(50.0),
):
    contents = await _read_upload(file)
    try:
        result = BiometricCompressor.compress_photograph(
            image_bytes=contents,
            target_width=max(100, min(target_width, 1200)),
            target_height=max(100, min(target_height, 1200)),
            min_kb=max(1.0, min(min_kb, 500.0)),
            max_kb=max(2.0, min(max_kb, 500.0)),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read that image. Please upload a JPEG or PNG.") from exc
    vault_mgr.vault.photo_path = result["file_path"]
    vault_mgr.save(vault_mgr.vault)
    return result


@app.post("/api/biometrics/compress-signature")
async def compress_signature(
    file: UploadFile = File(...),
    target_width: int = Form(140),
    target_height: int = Form(60),
    min_kb: float = Form(10.0),
    max_kb: float = Form(20.0),
):
    contents = await _read_upload(file)
    try:
        result = BiometricCompressor.compress_signature(
            image_bytes=contents,
            target_width=max(40, min(target_width, 800)),
            target_height=max(20, min(target_height, 400)),
            min_kb=max(1.0, min(min_kb, 500.0)),
            max_kb=max(2.0, min(max_kb, 500.0)),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read that image. Please upload a JPEG or PNG.") from exc
    vault_mgr.vault.signature_path = result["file_path"]
    vault_mgr.save(vault_mgr.vault)
    return result


@app.get("/api/biometrics/preview")
def get_biometrics_preview():
    BiometricCompressor.generate_sample_assets()
    photo_p = settings.UPLOADS_DIR / "candidate_photo.jpg"
    sig_p = settings.UPLOADS_DIR / "candidate_signature.jpg"
    photo_kb = round(photo_p.stat().st_size / 1024.0, 2) if photo_p.exists() else 0
    sig_kb = round(sig_p.stat().st_size / 1024.0, 2) if sig_p.exists() else 0
    return {
        "photo": {
            "path": "/uploads/candidate_photo.jpg",
            "size_kb": photo_kb,
            "target_spec": "20KB - 50KB JPEG (350x350 px)",
            "in_spec": 20.0 <= photo_kb <= 50.0,
        },
        "signature": {
            "path": "/uploads/candidate_signature.jpg",
            "size_kb": sig_kb,
            "target_spec": "10KB - 20KB JPEG (140x60 px)",
            "in_spec": 10.0 <= sig_kb <= 20.0,
        },
    }


# --------------------------------------------------------------------------- engine


@app.get("/api/engine/config")
def get_engine_config():
    return tinyfish_client.public_config()


@app.post("/api/engine/config")
def update_engine_config(config: EngineConfig):
    tinyfish_client.save_config(config)
    return {"success": True, "config": tinyfish_client.public_config()}


@app.post("/api/engine/test-tinyfish")
async def test_tinyfish(payload: Dict[str, Any]):
    api_key = payload.get("api_key") or payload.get("tinyfish_api_key")
    if api_key in {"", "***", "********"}:
        api_key = None
    return await tinyfish_client.test_connection(api_key=api_key)


@app.get("/api/engine/wallet")
async def get_wallet():
    try:
        wallet = await tinyfish_client.get_wallet()
        return {
            "available_balance": wallet.get("available_balance"),
            "currency": wallet.get("currency"),
            "as_of": wallet.get("as_of"),
        }
    except TinyFishError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# --------------------------------------------------------------------------- health / runs


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "demo_mode": settings.DEMO_MODE,
        "auth_required": settings.AUTH_REQUIRED,
        "simulator_enabled": settings.ENABLE_SIMULATOR,
        "tinyfish_configured": tinyfish_client.is_configured,
        "effective_mode": tinyfish_client.effective_mode(),
        "active_run": orchestrator.run_id,
        "state": orchestrator.state,
        "run_mode": orchestrator.run_mode,
        "live_browser_sessions": len(live_sessions.active()),
        "inspect_ready": orchestrator.state == "INSPECT_READY",
    }


@app.get("/api/runs")
def list_runs(limit: int = Query(25, ge=1, le=100)):
    return {"runs": run_store.list_runs(limit=limit)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    meta = run_store.read_meta(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {
        "meta": meta,
        "events": run_store.read_events(run_id),
        "audit": run_store.read_audit(run_id),
    }


@app.get("/api/runs/{run_id}/audit")
def get_run_audit(run_id: str):
    audit = run_store.read_audit(run_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit report not found.")
    return JSONResponse(content=audit, headers={"Content-Disposition": f'attachment; filename="formpilot-audit-{run_id}.json"'})


# --------------------------------------------------------------------------- recipes


@app.get("/api/recipes")
def list_recipes():
    return {"recipes": orchestrator.recipe_store.list_recipes()}


@app.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: str):
    recipe = orchestrator.recipe_store.load_by_id(recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    return recipe


# --------------------------------------------------------------------------- agent


class LaunchRequest(BaseModel):
    query_or_url: str = Field(..., min_length=1, max_length=500)
    mode: str = Field("fill", pattern="^(fill|inspect)$")


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class EntryModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(register|login|resume)$")


@app.post("/api/agent/start")
async def start_agent(req: LaunchRequest):
    if orchestrator.is_running:
        return {"success": False, "message": "An application is already in progress."}
    if orchestrator.page and not orchestrator.page.is_closed() and orchestrator.state in {"INSPECT_READY", "AWAITING_PAYMENT"}:
        await orchestrator.stop()
    task = asyncio.create_task(orchestrator.start_application(req.query_or_url, req.mode))
    app.state.agent_task = task

    def _done(done_task: asyncio.Task):
        try:
            done_task.result()
        except Exception:
            traceback.print_exc()

    task.add_done_callback(_done)
    return {
        "success": True,
        "message": "Inspection started." if req.mode == "inspect" else "Application started.",
        "mode": req.mode,
        "run_id": orchestrator.run_id,
    }


@app.post("/api/agent/entry-mode")
async def choose_entry_mode(req: EntryModeRequest):
    """Select register/login/resume explicitly, without guessing."""
    result = orchestrator.choose_entry_mode(req.mode)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("message") or "That entry path is not available.")
    await broadcast_to_cockpits(
        {
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "phase": "DECIDE",
            "message": result.get("message") or "Entry path selected.",
            "state": orchestrator.state,
            "run_id": orchestrator.run_id,
            "entry_mode": orchestrator._entry_mode,
            "entry_options": orchestrator.get_state().get("entry_options") or [],
            "fill_summary": orchestrator.fill_summary,
        }
    )
    return result


@app.post("/api/agent/inspect/scan")
async def inspect_current_page():
    try:
        form_map = await orchestrator.refresh_inspection()
    except AgentRunError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "form_map": form_map, "recipe": orchestrator._recipe_status}


@app.post("/api/agent/upload")
async def upload_for_portal(
    field_key: str = Form(..., min_length=1, max_length=80),
    file: UploadFile = File(...),
):
    if not orchestrator.page or orchestrator.page.is_closed():
        raise HTTPException(status_code=409, detail="There is no live browser to upload to.")
    if not re.match(r"^[a-zA-Z0-9_\-]{1,80}$", field_key):
        raise HTTPException(status_code=422, detail="Invalid field key.")

    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The file must be 5 MB or smaller.")
    content_type = (file.content_type or "").lower()
    allowed = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }
    if content_type not in allowed:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG, WEBP or PDF file.")

    original = Path(file.filename or "upload").name
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original).stem)[:60] or "upload"
    destination = settings.UPLOADS_DIR / f"user-{uuid.uuid4().hex[:10]}-{safe_stem}{allowed[content_type]}"
    destination.write_bytes(data)

    result = await orchestrator.attach_upload(str(destination), field_key)
    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("message") or "The portal did not accept the file.")
    return result


@app.post("/api/agent/pause")
async def pause_agent():
    if not orchestrator.is_running:
        return {"success": False, "message": "There is no active application to pause."}
    if orchestrator.state == "WAITING_FOR_USER":
        return {
            "success": False,
            "message": "The agent is already waiting for your input at a checkpoint.",
        }
    if orchestrator.state not in {"RUNNING", "RESOLVING"}:
        return {
            "success": False,
            "message": "The agent is not currently working, so there is nothing to pause.",
        }
    orchestrator.pause()
    await broadcast_to_cockpits(
        {
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "phase": "DECIDE",
            "message": "Application paused. Take your time to review.",
            "state": orchestrator.state,
            "run_id": orchestrator.run_id,
        }
    )
    return {"success": True, "state": orchestrator.state}


@app.post("/api/agent/resume")
async def resume_agent():
    if not orchestrator.is_running:
        return {"success": False, "message": "There is no active application to resume."}
    if not orchestrator.paused:
        return {"success": False, "message": "The application is already running."}
    orchestrator.resume()
    await broadcast_to_cockpits(
        {
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "phase": "ACT",
            "message": "Application resumed.",
            "state": orchestrator.state,
            "run_id": orchestrator.run_id,
        }
    )
    return {"success": True, "state": orchestrator.state}


@app.post("/api/agent/stop")
async def stop_agent():
    await orchestrator.stop()
    return {"success": True, "message": "Application stopped."}


@app.post("/api/agent/reset")
async def reset_agent():
    if not await orchestrator.reset_session():
        return {
            "success": False,
            "message": "Stop the active application before starting a new one.",
        }
    await broadcast_to_cockpits(
        {
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "phase": "DECIDE",
            "message": "Ready for a new application.",
            "state": "IDLE",
            "run_id": None,
            "active_gate": None,
            "run_mode": "fill",
        }
    )
    return {"success": True, "state": "IDLE"}


@app.post("/api/agent/dismiss-gate")
async def dismiss_gate():
    if orchestrator.active_gate:
        orchestrator.active_gate = None
        orchestrator.submit_user_response({"action": "DISMISS"})
    return {"success": True}


@app.post("/api/agent/user-response")
def submit_candidate_response(data: Dict[str, Any]):
    if len(json.dumps(data)) > 50_000:
        raise HTTPException(status_code=413, detail="Response is too large.")
    if not orchestrator.active_gate and not orchestrator.active_event_future:
        return {"success": False, "message": "There is no open checkpoint."}
    orchestrator.submit_user_response(data)
    return {"success": True}


@app.get("/api/agent/state")
def get_agent_state():
    return orchestrator.get_state()


# --------------------------------------------------------------------------- chat


@app.post("/api/chat/message")
async def post_chat_message(req: ChatMessageRequest):
    result = await chat_assistant.handle_message(req.message)
    await broadcast_to_cockpits(
        {
            "timestamp": result.get("timestamp", datetime.datetime.now().strftime("%H:%M")),
            "type": "CHAT_MESSAGE",
            "sender": chat_assistant.sender,
            "message": result.get("reply", ""),
            "action_taken": result.get("action_taken"),
            "field_updated": result.get("field_updated"),
            "new_value": result.get("new_value"),
            "entry_mode": result.get("entry_mode"),
            "login_method": result.get("login_method"),
            "login_identifier": result.get("login_identifier"),
            "fill_summary": orchestrator.fill_summary,
            "fill_failures": orchestrator.fill_failures,
        }
    )
    return result


@app.get("/api/chat/history")
def get_chat_history():
    return chat_assistant.chat_history


# --------------------------------------------------------------------------- websocket


def _ws_token(websocket: WebSocket) -> str:
    auth = websocket.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return websocket.query_params.get("token") or websocket.headers.get("x-api-token") or ""


@app.websocket("/ws/live")
async def live_websocket(websocket: WebSocket):
    """Interactive stream of the agent's real browser.

    Frames are JPEG images from Chrome's CDP screencast.  Input is forwarded
    back to the same page.  The session token is separate from the cockpit
    token so another tab cannot take control of an active run.
    """
    session_id = websocket.query_params.get("session_id", "")
    access_token = websocket.query_params.get("access_token", "")
    session = live_sessions.get(session_id)
    if not session or not hmac.compare_digest(session.access_token, access_token):
        await websocket.close(code=1008)
        return
    if settings.AUTH_REQUIRED and not _safe_compare(_ws_token(websocket)):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    queue = session.subscribe()
    await websocket.send_json({"type": "hello", **session.public_info()})
    # A static page may not produce another frame after the browser session
    # starts. Send the latest frame on connect so a late subscriber sees the
    # real page immediately instead of an empty viewer.
    latest_frame = session.latest_frame_base64()
    if latest_frame:
        await websocket.send_json(
            {
                "type": "frame",
                "data": latest_frame,
                "metadata": session._latest_metadata,
                "viewport": session.public_info()["viewport"],
                "url": session.public_info()["url"],
                "frames_sent": session.frames_sent,
            }
        )

    async def sender():
        while True:
            message = await queue.get()
            await websocket.send_json(message)

    send_task = asyncio.create_task(sender())
    window_start = time.monotonic()
    message_count = 0
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 12_000:
                await websocket.send_json({"type": "input_error", "error": "Input message is too large."})
                continue
            message_count += 1
            now = time.monotonic()
            if now - window_start >= 1.0:
                window_start = now
                message_count = 0
            if message_count > 180:
                await websocket.send_json({"type": "input_error", "error": "Too many input events. Slow down."})
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "input_error", "error": "Invalid JSON."})
                continue
            result = await session.dispatch(data)
            if not result.get("ok"):
                await websocket.send_json({"type": "input_error", **result})
    except WebSocketDisconnect:
        pass
    except Exception:
        traceback.print_exc()
    finally:
        send_task.cancel()
        session.unsubscribe(queue)


@app.websocket("/ws/cockpit")
async def cockpit_websocket(websocket: WebSocket):
    if settings.AUTH_REQUIRED and not _safe_compare(_ws_token(websocket)):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    active_connections.append(websocket)
    try:
        await websocket.send_json(
            {
                "timestamp": "Ready",
                "phase": "SENSE",
                "message": "FormPilot is connected. Start an application whenever you are ready.",
                "hindi": "FormPilot connected hai. Jab chahein application shuru karein.",
                "screenshot": "",
                "active_gate": orchestrator.active_gate,
                "current_section": orchestrator.current_section,
                "filled_audit": orchestrator._public_audit(),
                "run_id": orchestrator.run_id,
                "state": orchestrator.state,
                "run_mode": orchestrator.run_mode,
                "live_session": orchestrator.live.public_info() if orchestrator.live and not orchestrator.live.closed else None,
                "form_map": orchestrator.form_map,
                "recipe": orchestrator._recipe_status,
                "fill_summary": orchestrator.fill_summary,
                "fill_failures": orchestrator.fill_failures,
                "entry_mode": orchestrator._entry_mode,
                "entry_options": orchestrator.get_state().get("entry_options") or [],
                "login_method": orchestrator._login_method,
                "login_identifier": orchestrator._login_identifier,
            }
        )
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "ERROR", "message": "Invalid message."})
                continue
            action = data.get("action")
            if action == "SUBMIT_GATE":
                orchestrator.submit_user_response(data.get("payload", {}))
            elif action == "SEND_CHAT":
                message = str(data.get("message", ""))[:2000]
                result = await chat_assistant.handle_message(message)
                await broadcast_to_cockpits(
                    {
                        "timestamp": result.get("timestamp", datetime.datetime.now().strftime("%H:%M")),
                        "type": "CHAT_MESSAGE",
                        "sender": chat_assistant.sender,
                        "message": result.get("reply", ""),
                        "action_taken": result.get("action_taken"),
                        "field_updated": result.get("field_updated"),
                        "new_value": result.get("new_value"),
                        "entry_mode": result.get("entry_mode"),
                        "login_method": result.get("login_method"),
                        "login_identifier": result.get("login_identifier"),
                        "fill_summary": orchestrator.fill_summary,
                        "fill_failures": orchestrator.fill_failures,
                    }
                )
            elif action == "PING":
                await websocket.send_json({"type": "PONG", "timestamp": datetime.datetime.now().isoformat()})
    except WebSocketDisconnect:
        pass
    except Exception:
        traceback.print_exc()
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)


# --------------------------------------------------------------------------- protected uploads


_UPLOAD_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


@app.get("/uploads/{filename}")
def get_upload(filename: str):
    if not _UPLOAD_NAME_RE.match(filename) or ".." in filename:
        raise HTTPException(status_code=404, detail="File not found.")
    path = settings.UPLOADS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    media_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "application/octet-stream"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- static frontend

FRONTEND_DIST = settings.ROOT_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
