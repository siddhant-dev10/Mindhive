"""AgentHive Main FastAPI Application.
Hosts the Switch Agent Protocol bridge, the Orchestration Engine,
Discord command webhooks, and the Real-time Dashboard UI.
"""

import os
import logging
import shutil
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import httpx
import importlib
import hmac
import time
from agenthive.web_auth import (
    SESSION_TTL_SECONDS,
    issue_dashboard_session,
    verify_dashboard_session,
    verify_csrf,
)

from agenthive.config import settings
from agenthive.database import db
from agenthive.switch.server import router as switch_router, switch_state
import asyncio
from agenthive.discord_gateway.bot import discord_dispatcher, start_discord_bot
from agenthive.engine.orchestrator import orchestrator
from agenthive.models.project import ProjectCreate
from agenthive.voice.wispr import wispr_integration

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("agenthive.main")

_docker_probe = {"checked_at": 0.0, "status": "unknown", "version": None}
_dashboard_login_attempts: Dict[str, list] = {}
_switch_retry_task: Optional[asyncio.Task] = None
_discord_gateway_task: Optional[asyncio.Task] = None


def _official_switch_ready() -> bool:
    return all(
        agent.client
        and agent.client.is_official_switch
        and agent.client.is_connected
        and agent.client._sse_ready.is_set()
        for agent in orchestrator.agents
    )


async def _retry_official_switch_connections():
    delay = 2.0
    while not _official_switch_ready():
        pending = [agent for agent in orchestrator.agents if not agent.client or not agent.client.is_connected]
        if pending:
            results = await asyncio.gather(
                *(agent.connect_to_switch(settings.switch_core_url) for agent in pending),
                return_exceptions=True,
            )
            for agent, result in zip(pending, results):
                if isinstance(result, Exception):
                    logger.warning("Official Switch reconnection failed for %s (%s)", agent.agent_id, type(result).__name__)
        if _official_switch_ready():
            logger.info("All AgentHive agents reconnected to Official Switch")
            return
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register each configured participant with the selected Switch transport.
    results = await asyncio.gather(
        *(agent.connect_to_switch(settings.switch_core_url) for agent in orchestrator.agents),
        return_exceptions=True,
    )
    for agent, result in zip(orchestrator.agents, results):
        if isinstance(result, Exception):
            logger.error("Switch connection failed for %s (%s)", agent.agent_id, type(result).__name__)
        elif agent.client:
            logger.info(
                "Switch connection established for %s (transport=%s)",
                agent.agent_id,
                "official" if agent.client.is_official_switch else "local fallback",
            )

    global _discord_gateway_task, _switch_retry_task
    if settings.discord_bot_token:
        logger.info("Initializing live Discord gateway task...")
        _discord_gateway_task = asyncio.create_task(start_discord_bot())
    if settings.switch_mode == "official" and not _official_switch_ready():
        logger.error("Official Switch is degraded; collaboration commands will fail closed while reconnect retries run")
        _switch_retry_task = asyncio.create_task(_retry_official_switch_connections())

    yield

    for task in (_switch_retry_task, _discord_gateway_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
    _switch_retry_task = None
    _discord_gateway_task = None
    bot_module = importlib.import_module("agenthive.discord_gateway.bot")
    live_bot = bot_module.live_discord_bot
    if live_bot and not live_bot.is_closed():
        await live_bot.close()
    await asyncio.gather(
        *(agent.client.disconnect() for agent in orchestrator.agents if agent.client),
        return_exceptions=True,
    )


app = FastAPI(
    title="AgentHive",
    description="Multi-Agent AI Collaboration Platform powered by Switch Protocol",
    version="1.0.0",
    lifespan=lifespan,
)


class DashboardLoginRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)


class DashboardRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


def _request_is_loopback(request: Request) -> bool:
    client_host = request.client.host if request.client else ""
    try:
        import ipaddress
        return ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        return False


def _request_origin_is_allowed(request: Request, *, required: bool = False) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return not required
    return origin in settings.dashboard_allowed_origins


def _login_rate_allowed(client_host: str) -> bool:
    now = time.monotonic()
    attempts = [stamp for stamp in _dashboard_login_attempts.get(client_host, []) if now - stamp < 300]
    _dashboard_login_attempts[client_host] = attempts
    return len(attempts) < 5


def _record_login_failure(client_host: str) -> None:
    now = time.monotonic()
    _dashboard_login_attempts[client_host] = [
        stamp for stamp in _dashboard_login_attempts.get(client_host, []) if now - stamp < 300
    ] + [now]


def _dashboard_session(request: Request):
    session = verify_dashboard_session(
        request.cookies.get("agenthive_session"),
        settings.dashboard_api_token,
    )
    if not session or not settings.discord_owner_id or session.subject != str(settings.discord_owner_id):
        return None
    return session


def _require_project_owner(project_id: str, owner_id: str):
    project = orchestrator.get_project(project_id)
    if not project or not project.owner_discord_id or str(project.owner_discord_id) != str(owner_id):
        # Do not reveal whether another owner's project exists.
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _docker_runtime_status() -> Dict[str, Any]:
    """Return observed Docker daemon health, cached to avoid polling on every dashboard refresh."""
    if _docker_probe["checked_at"] and time.monotonic() - _docker_probe["checked_at"] < 15:
        return {key: value for key, value in _docker_probe.items() if key != "checked_at"}
    _docker_probe["checked_at"] = time.monotonic()
    docker = shutil.which("docker")
    if not docker:
        _docker_probe.update(status="unavailable", version=None)
    else:
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                docker, "info", "--format", "{{.ServerVersion}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
            version = stdout.decode(errors="replace").strip()
            _docker_probe.update(status="online" if process.returncode == 0 and version else "offline", version=version or None)
        except Exception:
            try:
                if process is not None:
                    process.kill()
                    await process.wait()
            except Exception:
                pass
            _docker_probe.update(status="offline", version=None)
    return {key: value for key, value in _docker_probe.items() if key != "checked_at"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.dashboard_allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def guard_authenticated_api(request: Request, call_next):
    """Protect private API reads and every mutation with an owner session + CSRF."""
    if request.url.path.startswith("/switch/api/v1") and request.url.path != "/switch/api/v1/health/ready":
        switch_token = settings.switch_registration_token or settings.switch_api_key
        authorization = request.headers.get("authorization", "")
        presented = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        if not switch_token or not hmac.compare_digest(presented, switch_token):
            return JSONResponse({"detail": "Local Switch bridge authentication failed"}, status_code=403)

    if request.url.path.startswith("/api/") and request.url.path != "/api/auth/session" and request.method != "OPTIONS":
        session = _dashboard_session(request)
        if not session:
            return JSONResponse({"detail": "Dashboard owner session required"}, status_code=401, headers={"Cache-Control": "no-store"})
        request.state.dashboard_session = session

        mutation = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        if mutation:
            if not _request_is_loopback(request):
                return JSONResponse({"detail": "Dashboard mutations are available only to loopback clients"}, status_code=403)
            if not _request_origin_is_allowed(request, required=True):
                return JSONResponse({"detail": "Cross-origin or missing-origin mutation rejected"}, status_code=403)
            if not verify_csrf(session, request.headers.get("x-csrf-token")):
                return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
    return await call_next(request)

# Mount Switch Agent Protocol Router
app.include_router(switch_router)

# Mount UI static assets
UI_DIR = Path(__file__).parent / "ui"
UI_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the premium dark mode AgentHive Live Dashboard."""
    index_file = UI_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text())
    return HTMLResponse("<h1>AgentHive API Active</h1><p>Visit /docs for Swagger API</p>")

@app.get("/api/status")
async def get_system_status():
    """Return observed runtime state; availability is not the same as connection."""
    with db.get_connection() as conn:
        proj_count = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]
        task_count = conn.execute("SELECT COUNT(*) as c FROM tasks").fetchone()["c"]

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            switch_response = await client.get(f"{settings.switch_core_url.rstrip('/')}/health/ready")
        switch_ready = switch_response.status_code == 200 and switch_response.json().get("status") == "ready"
    except Exception:
        switch_ready = False

    discord_bot_module = importlib.import_module("agenthive.discord_gateway.bot")
    live_bot = discord_bot_module.live_discord_bot
    # Status reads the last observed state only; dashboard refreshes must not trigger an external API call.
    gemini_health = dict(orchestrator.gemini.last_health_status)
    docker_status = await _docker_runtime_status()

    official_room_count = None
    for agent in orchestrator.agents:
        if agent.client and agent.client.is_official_switch:
            try:
                official_room_count = len(await agent.client.list_rooms())
            except Exception as exc:
                logger.warning("Could not verify official Switch room list (%s)", type(exc).__name__)
            break

    agent_statuses = []
    for agent in orchestrator.agents:
        connected = bool(
            agent.client
            and agent.client.is_connected
            and agent.client._sse_ready.is_set()
        )
        if agent.agent_id == "agent-codex":
            available = agent.is_cli_available
            mode = "Native Codex CLI available; execution not verified" if available else "Codex local fallback (CLI unavailable)"
        elif agent.agent_id == "agent-agy":
            available = agent.is_cli_available
            mode = "Native AGY CLI available; execution not verified" if available else "AGY local fallback (CLI unavailable)"
        elif agent.agent_id == "agent-gemini":
            available = gemini_health["available"]
            mode = gemini_health["mode"]
        else:
            daemon_live = agent.runtime_adapter.is_daemon_connected
            available = daemon_live or agent.runtime_adapter.is_binary_available
            mode = "Hermes daemon healthy; request not verified" if daemon_live else (
                "Hermes CLI available (not connected)" if agent.runtime_adapter.is_binary_available
                else "LOCAL GOVERNANCE FALLBACK"
            )
        agent_statuses.append({
            "id": agent.agent_id,
            "name": agent.name,
            "role": agent.role,
            "status": "Connected" if connected else ("Disconnected" if agent.client else "Not connected"),
            "runtime_mode": mode,
            "runtime_available": available,
            "switch_transport": "Official Switch" if agent.client and agent.client.is_official_switch else (
                "Local fallback" if agent.client else "Unavailable"
            ),
            "switch_connected": connected,
        })

    discord_online = bool(live_bot and live_bot.is_ready())
    guild_id = settings.discord_guild_id
    guild_commands = 0
    if discord_online and guild_id:
        from discord import Object
        guild_commands = len(live_bot.tree.get_commands(guild=Object(id=int(guild_id))))
    connected_count = sum(1 for a in orchestrator.agents if a.client and a.client.is_connected and a.client._sse_ready.is_set())
    registered_count = sum(1 for a in orchestrator.agents if a.client and a.client.is_official_switch and a.client.official_agent_id)
    official_transport = settings.switch_mode == "official" and all(
        a.client and a.client.is_official_switch for a in orchestrator.agents
    )
    hermes_status = orchestrator.hermes.get_runtime_status()

    return {
        "status": "healthy" if (
            switch_ready
            and official_transport
            and connected_count == len(orchestrator.agents)
            and discord_online
            and guild_commands == 9
            and bool(settings.discord_owner_id)
            and gemini_health["available"]
            and hermes_status["daemon_connected"]
            and docker_status["status"] == "online"
        ) else "degraded",
        "platform": "AgentHive",
        "tagline": "Many Minds. One Mission.",
        "switch_core": {
            "status": "online" if switch_ready else "offline",
            # Official Switch's list endpoint reports rooms visible to this agent,
            # not rooms currently active. Keep those concepts distinct.
            "active_rooms": None,
            "rooms_visible": official_room_count if official_room_count is not None else len(switch_state.rooms) if settings.switch_mode == "local" else None,
            "registered_agents": registered_count if official_transport else 0,
            "connected_agents": connected_count,
            "mode": "official" if official_transport else ("local fallback" if settings.switch_mode == "local" else "degraded"),
        },
        "docker": docker_status,
        "discord": {
            "status": "online" if discord_online else "offline",
            "guilds_connected": len(live_bot.guilds) if discord_online else 0,
            "owner_id_configured": bool(settings.discord_owner_id),
            "commands_registered": guild_commands,
        },
        "agents": agent_statuses,
        "external_runtimes": {
            "gemini": gemini_health,
            "hermes": hermes_status,
        },
        "database": {
            "projects_count": proj_count,
            "tasks_count": task_count,
            "engine": "SQLite WAL"
        },
        "ponytail": {
            "mode": settings.ponytail_mode,
            "enforce_stdlib_only": settings.ponytail_enforce_stdlib,
            "max_diff_lines": settings.ponytail_max_diff_lines,
        },
        "task_execution": {
            "status": "ready" if settings.task_execution_enabled and settings.secure_agent_task_runner_configured else "blocked",
            "runner_mode": "isolated native-agent runner" if settings.secure_agent_task_runner_configured else "not configured",
            "reason": None if settings.task_execution_enabled and settings.secure_agent_task_runner_configured else "Secure isolated native-agent runner is not implemented; host task execution is disabled.",
        },
        "wispr_flow": wispr_integration.get_status()
    }


@app.get("/api/auth/session")
async def get_dashboard_session(request: Request):
    session = _dashboard_session(request)
    response = JSONResponse(
        {"authenticated": bool(session), "csrf_token": session.csrf_token if session else None},
        headers={"Cache-Control": "no-store"},
    )
    return response


@app.post("/api/auth/session")
async def create_dashboard_session(payload: DashboardLoginRequest, request: Request):
    client_host = request.client.host if request.client else "unknown"
    if not _request_is_loopback(request) or not _request_origin_is_allowed(request):
        raise HTTPException(status_code=403, detail="Dashboard login is available only from an allowed local origin")
    if not _login_rate_allowed(client_host):
        raise HTTPException(status_code=429, detail="Too many dashboard login attempts; try again later")
    if not settings.dashboard_api_token or len(settings.dashboard_api_token) < 32:
        raise HTTPException(status_code=503, detail="Dashboard authentication is not securely configured")
    if not settings.discord_owner_id:
        raise HTTPException(status_code=503, detail="The project owner identity is not configured")
    if not hmac.compare_digest(payload.token, settings.dashboard_api_token):
        _record_login_failure(client_host)
        raise HTTPException(status_code=401, detail="Invalid dashboard credential")

    _dashboard_login_attempts.pop(client_host, None)
    session, cookie = issue_dashboard_session(str(settings.discord_owner_id), settings.dashboard_api_token)
    response = JSONResponse(
        {"authenticated": True, "csrf_token": session.csrf_token},
        headers={"Cache-Control": "no-store"},
    )
    response.set_cookie(
        "agenthive_session",
        cookie,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.dashboard_session_cookie_secure,
        samesite="strict",
        path="/",
    )
    return response


@app.delete("/api/auth/session")
async def delete_dashboard_session(request: Request):
    session = _dashboard_session(request)
    if not _request_is_loopback(request) or not _request_origin_is_allowed(request, required=True):
        raise HTTPException(status_code=403, detail="Dashboard sign-out requires an allowed local origin")
    if session and not verify_csrf(session, request.headers.get("x-csrf-token")):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    response = JSONResponse({"authenticated": False}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        "agenthive_session",
        path="/",
        secure=settings.dashboard_session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return response

# --- Project Lifecycle Endpoints (Mapping to Discord Slash Commands) ---

@app.post("/api/projects")
async def create_project_api(req: ProjectCreate, request: Request):
    """Corresponds to /newproject command."""
    actor_id = request.state.dashboard_session.subject
    return await discord_dispatcher.cmd_newproject(
        req.name,
        req.description,
        user_id=actor_id,
    )

@app.get("/api/projects")
async def list_projects_api(request: Request):
    actor_id = request.state.dashboard_session.subject
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM projects WHERE owner_discord_id = ? ORDER BY created_at DESC",
            (actor_id,),
        ).fetchall()
        return {"projects": [dict(r) for r in rows]}

@app.get("/api/projects/{project_id}")
async def get_project_api(project_id: str, request: Request):
    """Corresponds to /project and /status commands."""
    _require_project_owner(project_id, request.state.dashboard_session.subject)
    return await discord_dispatcher.cmd_status(project_id, actor_id=request.state.dashboard_session.subject)

@app.post("/api/projects/{project_id}/analyse")
async def analyse_project_api(project_id: str, request: Request):
    """Corresponds to /analyse command."""
    actor_id = request.state.dashboard_session.subject
    _require_project_owner(project_id, actor_id)
    return await discord_dispatcher.cmd_analyse(project_id, actor_id=actor_id)

@app.post("/api/projects/{project_id}/discuss")
async def discuss_project_api(project_id: str, request: Request):
    """Corresponds to /discuss command."""
    actor_id = request.state.dashboard_session.subject
    _require_project_owner(project_id, actor_id)
    return await discord_dispatcher.cmd_discuss(project_id, actor_id=actor_id)

@app.post("/api/projects/{project_id}/assign")
async def assign_project_api(project_id: str, request: Request):
    """Corresponds to /assign command."""
    actor_id = request.state.dashboard_session.subject
    _require_project_owner(project_id, actor_id)
    return await discord_dispatcher.cmd_assign(project_id, actor_id=actor_id)

@app.post("/api/projects/{project_id}/approve")
async def approve_project_api(project_id: str, request: Request, task_code: Optional[str] = None):
    actor_id = request.state.dashboard_session.subject
    _require_project_owner(project_id, actor_id)
    result = await discord_dispatcher.cmd_approve(project_id, task_code, actor_id=actor_id)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error", "Approval failed"))
    return result

@app.post("/api/projects/{project_id}/reject")
async def reject_project_api(project_id: str, payload: DashboardRejectRequest, request: Request):
    actor_id = request.state.dashboard_session.subject
    _require_project_owner(project_id, actor_id)
    result = await discord_dispatcher.cmd_reject(project_id, payload.reason, actor_id=actor_id)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error", "Rejection failed"))
    return result

@app.post("/api/projects/{project_id}/execute")
async def execute_project_api(project_id: str, request: Request):
    """Execution is a separate, explicit owner-authenticated action."""
    actor_id = request.state.dashboard_session.subject
    _require_project_owner(project_id, actor_id)
    result = await discord_dispatcher.cmd_report(project_id, actor_id=actor_id)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error", "Execution failed"))
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agenthive.main:app", host=settings.host, port=settings.port, reload=True)
