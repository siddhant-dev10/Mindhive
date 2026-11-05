"""AgentHive Main FastAPI Application.
Hosts the Switch Agent Protocol bridge, the Orchestration Engine,
Discord command webhooks, and the Real-time Dashboard UI.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

from agenthive.config import settings
from agenthive.database import db
from agenthive.switch.server import router as switch_router, switch_state
import asyncio
from agenthive.discord_gateway.bot import discord_dispatcher, start_discord_bot
from agenthive.models.project import ProjectCreate
from agenthive.voice.wispr import wispr_integration

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("agenthive.main")

app = FastAPI(
    title="AgentHive",
    description="Multi-Agent AI Collaboration Platform powered by Switch Protocol",
    version="1.0.0"
)

@app.on_event("startup")
async def on_startup():
    if settings.discord_bot_token:
        logger.info("Initializing live Discord gateway task...")
        asyncio.create_task(start_discord_bot())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    """Returns complete environment, Switch, and agent status."""
    with db.get_connection() as conn:
        proj_count = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]
        task_count = conn.execute("SELECT COUNT(*) as c FROM tasks").fetchone()["c"]

    return {
        "status": "healthy",
        "platform": "AgentHive",
        "tagline": "Many Minds. One Mission.",
        "switch_core": {
            "status": "online",
            "active_rooms": len(switch_state.rooms),
            "registered_agents": len(switch_state.agents)
        },
        "agents": [
            {"id": "agent-codex", "name": "ChatGPT Codex", "role": "Chief Backend Architect", "status": "Ready"},
            {"id": "agent-agy", "name": "AGY (Antigravity)", "role": "Systems Integration & CLI", "status": "Ready"},
            {"id": "agent-gemini", "name": "Google Gemini", "role": "Deep Reasoning & QA", "status": "Ready"},
            {"id": "agent-hermes", "name": "Hermes Supervisor", "role": "Autonomous Supervisor", "status": "Ready"}
        ],
        "database": {
            "projects_count": proj_count,
            "tasks_count": task_count,
            "engine": "SQLite WAL"
        },
        "wispr_flow": wispr_integration.get_status()
    }

# --- Project Lifecycle Endpoints (Mapping to Discord Slash Commands) ---

@app.post("/api/projects")
async def create_project_api(req: ProjectCreate):
    """Corresponds to /newproject command."""
    return await discord_dispatcher.cmd_newproject(req.name, req.description, req.po_discord_id)

@app.get("/api/projects")
async def list_projects_api():
    with db.get_connection() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return {"projects": [dict(r) for r in rows]}

@app.get("/api/projects/{project_id}")
async def get_project_api(project_id: str):
    """Corresponds to /project and /status commands."""
    return await discord_dispatcher.cmd_status(project_id)

@app.post("/api/projects/{project_id}/analyse")
async def analyse_project_api(project_id: str):
    """Corresponds to /analyse command."""
    return await discord_dispatcher.cmd_analyse(project_id)

@app.post("/api/projects/{project_id}/discuss")
async def discuss_project_api(project_id: str):
    """Corresponds to /discuss command."""
    return await discord_dispatcher.cmd_discuss(project_id)

@app.post("/api/projects/{project_id}/assign")
async def assign_project_api(project_id: str):
    """Corresponds to /assign command."""
    return await discord_dispatcher.cmd_assign(project_id)

@app.post("/api/projects/{project_id}/approve")
async def approve_project_api(project_id: str, task_code: Optional[str] = None):
    """Corresponds to /approve command."""
    return await discord_dispatcher.cmd_approve(project_id, task_code)

@app.post("/api/projects/{project_id}/reject")
async def reject_project_api(project_id: str, reason: str = "Rejected by Project Owner"):
    """Corresponds to /reject command."""
    return await discord_dispatcher.cmd_reject(project_id, reason)

@app.post("/api/projects/{project_id}/execute")
async def execute_project_api(project_id: str):
    """Corresponds to /report command."""
    return await discord_dispatcher.cmd_report(project_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agenthive.main:app", host=settings.host, port=settings.port, reload=True)
