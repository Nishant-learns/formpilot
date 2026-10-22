import os
import json
import asyncio
import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .core.vault import VaultManager, CandidateVault
from .core.oracle import SarkariOracle
from .core.biometrics import BiometricCompressor, UPLOADS_DIR
from .core.tinyfish_client import TinyFishClient, EngineConfig
from .core.orchestrator import CyberBhaiyaOrchestrator, CyberWaleBhaiyaOrchestrator
from .core.chat_assistant import CyberBhaiyaChatAssistant
from .simulator.portal import router as simulator_router

app = FastAPI(
    title="FormPilot API",
    version="1.0.0",
    description="Autonomous Career & Examination Operations AI Agent"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Simulator and Uploads
app.include_router(simulator_router)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Global instances
vault_mgr = VaultManager.get_instance()
tinyfish_client = TinyFishClient()

# Active WebSocket connections
active_connections: list[WebSocket] = []

async def broadcast_to_cockpits(event: Dict[str, Any]):
    """Broadcasts cognitive events and screenshots to connected Cockpit UIs."""
    disconnected = []
    for ws in active_connections:
        try:
            await ws.send_json(event)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_connections:
            active_connections.remove(ws)

orchestrator = CyberBhaiyaOrchestrator(broadcast_fn=broadcast_to_cockpits)
chat_assistant = CyberBhaiyaChatAssistant(orchestrator=orchestrator)

# ----------------- Candidate One-Vault Endpoints -----------------

@app.get("/api/vault")
def get_vault():
    """Retrieve candidate profile data."""
    return vault_mgr.vault.model_dump()

@app.post("/api/vault")
def update_vault(data: Dict[str, Any]):
    """Update Candidate One-Vault particulars."""
    updated = vault_mgr.update(data)
    return {"success": True, "vault": updated.model_dump()}

@app.post("/api/vault/custom-field")
def add_custom_field(field_name: str = Form(...), field_value: str = Form(...)):
    """Add or update an extensible custom field."""
    updated = vault_mgr.add_custom_field(field_name, field_value)
    return {"success": True, "vault": updated.model_dump()}

@app.post("/api/vault/reset")
def reset_vault():
    """Resets the One-Vault to high-fidelity default profile."""
    default_vault = CandidateVault()
    vault_mgr.save(default_vault)
    return {"success": True, "vault": default_vault.model_dump()}

# ----------------- Sarkari Oracle Endpoints -----------------

@app.get("/api/oracle/search")
def oracle_search(q: str = Query(..., description="Query or candidate wish or portal URL")):
    """Resolves natural language wish or URL through multi-source consensus."""
    res = SarkariOracle.resolve_target(q)
    return res.model_dump()

@app.get("/api/oracle/directory")
def get_verified_directory():
    """Returns authoritative registry of official recruitment portals."""
    from .core.oracle import OFFICIAL_PORTAL_REGISTRY
    return OFFICIAL_PORTAL_REGISTRY

# ----------------- Biometric Compression Pipeline Endpoints -----------------

@app.post("/api/biometrics/compress-photo")
async def compress_photo(
    file: UploadFile = File(...),
    target_width: int = Form(350),
    target_height: int = Form(350),
    min_kb: float = Form(20.0),
    max_kb: float = Form(50.0)
):
    """Enforces deterministic photograph compression to 20KB - 50KB JPEG (350x350)."""
    contents = await file.read()
    res = BiometricCompressor.compress_photograph(
        image_bytes=contents,
        target_width=target_width,
        target_height=target_height,
        min_kb=min_kb,
        max_kb=max_kb
    )
    # Update vault path
    vault_mgr.vault.photo_path = res["file_path"]
    vault_mgr.save(vault_mgr.vault)
    return res

@app.post("/api/biometrics/compress-signature")
async def compress_signature(
    file: UploadFile = File(...),
    target_width: int = Form(140),
    target_height: int = Form(60),
    min_kb: float = Form(10.0),
    max_kb: float = Form(20.0)
):
    """Enforces deterministic signature compression to 10KB - 20KB JPEG (140x60)."""
    contents = await file.read()
    res = BiometricCompressor.compress_signature(
        image_bytes=contents,
        target_width=target_width,
        target_height=target_height,
        min_kb=min_kb,
        max_kb=max_kb
    )
    # Update vault path
    vault_mgr.vault.signature_path = res["file_path"]
    vault_mgr.save(vault_mgr.vault)
    return res

@app.get("/api/biometrics/preview")
def get_biometrics_preview():
    """Generates sample test assets if not present and returns preview status."""
    BiometricCompressor.generate_sample_assets()
    photo_p = os.path.join(UPLOADS_DIR, "candidate_photo.jpg")
    sig_p = os.path.join(UPLOADS_DIR, "candidate_signature.jpg")
    
    photo_kb = round(os.path.getsize(photo_p) / 1024.0, 2) if os.path.exists(photo_p) else 0
    sig_kb = round(os.path.getsize(sig_p) / 1024.0, 2) if os.path.exists(sig_p) else 0

    return {
        "photo": {
            "path": "/uploads/candidate_photo.jpg",
            "size_kb": photo_kb,
            "target_spec": "20KB - 50KB JPEG (350x350 px)",
            "in_spec": 20.0 <= photo_kb <= 50.0
        },
        "signature": {
            "path": "/uploads/candidate_signature.jpg",
            "size_kb": sig_kb,
            "target_spec": "10KB - 20KB JPEG (140x60 px)",
            "in_spec": 10.0 <= sig_kb <= 20.0
        }
    }

# ----------------- Engine & TinyFish API Endpoints -----------------

@app.get("/api/engine/config")
def get_engine_config():
    """Returns engine configuration (Local Playwright vs TinyFish)."""
    return tinyfish_client.config.model_dump()

@app.post("/api/engine/config")
def update_engine_config(config: EngineConfig):
    """Updates engine settings."""
    tinyfish_client.save_config(config)
    return {"success": True, "config": tinyfish_client.config.model_dump()}

@app.post("/api/engine/test-tinyfish")
async def test_tinyfish(payload: Dict[str, Any]):
    """Tests TinyFish API connectivity with provided or stored credentials."""
    api_key = payload.get("api_key")
    res = await tinyfish_client.test_connection(api_key=api_key)
    return res

# ----------------- Autonomous Agent Control Endpoints -----------------

class LaunchRequest(BaseModel):
    query_or_url: str

@app.post("/api/agent/start")
async def start_agent(req: LaunchRequest):
    """Spawns CyberBhaiya on target recruitment URL or query."""
    if orchestrator.is_running:
        return {"success": False, "message": "Agent is already actively navigating a portal."}

    # Run in background task
    asyncio.create_task(orchestrator.start_application(req.query_or_url))
    return {"success": True, "message": "CyberBhaiya application sequence started."}

@app.post("/api/agent/stop")
async def stop_agent():
    """Emergency stops the agent and clears any active modal gate."""
    orchestrator.active_gate = None
    if orchestrator.active_event_future and not orchestrator.active_event_future.done():
        orchestrator.active_event_future.set_result({"action": "STOPPED"})
    await orchestrator.stop()
    await broadcast_to_cockpits({
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        "phase": "DECIDE",
        "message": "CyberBhaiya stopped. Checkpoints dismissed.",
        "hindi": "Agent rok diya gaya hai.",
        "active_gate": None
    })
    return {"success": True, "message": "CyberBhaiya safely stopped."}

@app.post("/api/agent/dismiss-gate")
async def dismiss_gate():
    """Dismisses currently active human checkpoint without stopping entire agent."""
    orchestrator.active_gate = None
    if orchestrator.active_event_future and not orchestrator.active_event_future.done():
        orchestrator.active_event_future.set_result({"action": "DISMISS"})
    await broadcast_to_cockpits({
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        "phase": "DECIDE",
        "message": "Checkpoint dismissed by user.",
        "hindi": "Checkpoint close kar diya gaya hai.",
        "active_gate": None
    })
    return {"success": True}

@app.post("/api/agent/user-response")
def submit_candidate_response(data: Dict[str, Any]):
    """Receives candidate interaction response (gateway choice, missing field, captcha, approval)."""
    orchestrator.submit_user_response(data)
    return {"success": True}

# ----------------- CyberBhaiya Live Chat Endpoints -----------------

class ChatMessageRequest(BaseModel):
    message: str

@app.post("/api/chat/message")
async def post_chat_message(req: ChatMessageRequest):
    """Processes candidate chat message, executes live edits or queries."""
    res = await chat_assistant.handle_message(req.message)
    # Broadcast to all connected cockpits
    await broadcast_to_cockpits({
        "timestamp": res.get("timestamp", datetime.datetime.now().strftime("%H:%M")),
        "type": "CHAT_MESSAGE",
        "sender": "CyberBhaiya",
        "message": res.get("reply", ""),
        "action_taken": res.get("action_taken"),
        "field_updated": res.get("field_updated"),
        "new_value": res.get("new_value")
    })
    return res

@app.get("/api/chat/history")
def get_chat_history():
    """Returns conversation history between candidate and CyberBhaiya."""
    return chat_assistant.chat_history

# ----------------- WebSocket Cockpit Feed -----------------

@app.websocket("/ws/cockpit")
async def cockpit_websocket(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        # Send initial greeting state
        await websocket.send_json({
            "timestamp": "Ready",
            "phase": "SENSE",
            "message": "CyberBhaiya Cockpit Online. Connected to backend agent engine.",
            "hindi": "Namaste! Mai hoon CyberBhaiya. Form bharne ke liye portal ya wish batayein.",
            "screenshot": "",
            "active_gate": orchestrator.active_gate,
            "current_section": orchestrator.current_section,
            "filled_audit": orchestrator.filled_audit
        })
        while True:
            # Keep socket open and receive any client messages
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
                if data.get("action") == "SUBMIT_GATE":
                    orchestrator.submit_user_response(data.get("payload", {}))
                elif data.get("action") == "SEND_CHAT":
                    user_msg = data.get("message", "")
                    res = await chat_assistant.handle_message(user_msg)
                    await broadcast_to_cockpits({
                        "timestamp": res.get("timestamp", datetime.datetime.now().strftime("%H:%M")),
                        "type": "CHAT_MESSAGE",
                        "sender": "CyberBhaiya",
                        "message": res.get("reply", ""),
                        "action_taken": res.get("action_taken"),
                        "field_updated": res.get("field_updated"),
                        "new_value": res.get("new_value")
                    })
            except Exception as e:
                print(f"[WebSocket] Error handling client message: {e}")
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

# ----------------- Serve Built Frontend SPA -----------------
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

