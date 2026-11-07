# AGENTHIVE V2 — FINAL ACTIVATION GUIDE
**Target System:** AgentHive V2 Multi-Agent Collaborative Framework  
**Document:** `FINAL_ACTIVATION_GUIDE.md`  
**Role:** Release Manager & Lead Integration Engineer  
**Date:** November 7, 2026  
**Audience:** Project Owner, Judges, Integration Engineers  

---

## 1. System Overview & Architecture

AgentHive V2 operates as an integrated multi-agent system comprising:
1. **Official Switch Collaboration Core** (`ghcr.io/sandbox-quantum/switch-core:latest`) on port `8080` (with PostgreSQL 16 on port `5433`).
2. **AgentHive Core Backend & Live Dashboard** (FastAPI / Uvicorn) on port `8000`.
3. **Discord Sovereign Command Centre** (`discord.Client` with 9 slash commands & interactive approval views).
4. **Quad Autonomous Agent Swarm**:
   - **ChatGPT Codex**: Chief Backend Architect (Native CLI, session tracking, pure stdlib synthesis).
   - **AGY (Antigravity)**: Systems Integration & CLI Automation (Native CLI, sandboxed execution).
   - **Google Gemini**: Deep Reasoning & Adversarial QA (Dual-mode REST API & local adversarial engine).
   - **Hermes Supervisor**: Autonomous Synthesis & Conflict Resolution (Dual-mode daemon & standalone governance).
5. **Pony Tail Engineering Guard**: Strict enforcement of 0 external pip dependencies.

---

## 2. Infrastructure Prerequisites

| Component | Minimum Version | Verified Local Status |
| :--- | :--- | :--- |
| **Operating System** | macOS 14+ (Darwin arm64 / Apple Silicon) | Darwin 24.x arm64 |
| **Python** | 3.9+ (Python 3.11 recommended for sandboxes) | Python 3.9.6 (venv: `./venv`) |
| **Docker Engine** | 24.0+ (Docker Desktop / Compose v2) | Docker v29.9.2 Active |
| **Official Switch Image** | `ghcr.io/sandbox-quantum/switch-core:latest` | Container verified healthy |
| **PostgreSQL Image** | `postgres:16-alpine` | Container verified healthy |
| **Codex CLI Binary** | `0.166.0-alpha.5.1` | Installed at `/Applications/ChatGPT.app/.../codex` |
| **AGY CLI Binary** | `1.5.x` | Installed at `/Users/sidh._./.local/bin/agy` |

---

## 3. Port Allocation & Conflict Prevention

Before starting the stack, verify that required ports are available:

| Port | Service | Bound Interface | Conflict Resolution |
| :--- | :--- | :--- | :--- |
| **8080** | Official Switch Core REST/SSE | `127.0.0.1:8080` | `lsof -i :8080` -> Kill conflicting process |
| **8082** | Switch WebSocket / Metrics | `127.0.0.1:8082` | `lsof -i :8082` -> Kill conflicting process |
| **5433** | Switch PostgreSQL 16 | `127.0.0.1:5433` | Dedicated port 5433 avoids standard 5432 conflict |
| **8000** | AgentHive API & Dashboard UI | `0.0.0.0:8000` | `lsof -i :8000` -> Kill conflicting process |
| **8686** | Optional Hermes Daemon | `127.0.0.1:8686` | Auto-detects; operates standalone if unassigned |

---

## 4. Single-Command Startup Sequence

Follow these exact steps from `/Users/sidh._./mindhive`:

### Step 1: Launch the Official Switch Infrastructure
```bash
cd /Users/sidh._./mindhive
docker compose -f docker-compose.switch.yml up -d
```

### Step 2: Verify Switch Subsystem Readiness
```bash
curl -s http://127.0.0.1:8080/health/ready
```
**Expected Output:**
```json
{
  "status": "ready",
  "checks": {
    "database": {"healthy": true},
    "message_listener": {"healthy": true},
    "session_activity_listener": {"healthy": true},
    "agent_event_listener": {"healthy": true},
    "signal_bus": {"healthy": true},
    "bridges": {"healthy": true},
    "connectors": {"healthy": true}
  }
}
```

### Step 3: Initialize Environment Variables
Copy template and configure environment secrets:
```bash
cp .env.example .env
```
Ensure `.env` contains:
```bash
# Core Configuration
ENVIRONMENT=development
LOG_LEVEL=INFO
AGENTHIVE_HOST=0.0.0.0
AGENTHIVE_PORT=8000
DATABASE_URL=sqlite:///./data/agenthive.db
WORKSPACE_ROOT=/Users/sidh._./mindhive/workspaces

# Switch Configuration
SWITCH_MODE=official
SWITCH_CORE_URL=http://localhost:8080
SWITCH_REGISTRATION_TOKEN=[REDACTED_SWITCH_API_KEY]

# Discord Gateway (Populate from Step 5)
DISCORD_BOT_TOKEN=<your_discord_bot_token>
DISCORD_APPLICATION_ID=<your_discord_application_id>
DISCORD_GUILD_ID=<your_mindhive_guild_id>
```

### Step 4: Start AgentHive Backend & Live Dashboard
```bash
./venv/bin/python -m uvicorn agenthive.main:app --host 0.0.0.0 --port 8000 --reload
```
Open **[http://localhost:8000](http://localhost:8000)** in any web browser to view the AgentHive Live Command Dashboard.

---

## 5. Discord Command Centre Activation Checklist

Follow this exact checklist to bring the live bot online in the **MindHive** Discord server:

### 1. Discord Developer Portal Setup
1. Open the **[Discord Developer Portal](https://discord.com/developers/applications)**.
2. Select your application (or create a new application named `AgentHive`).
3. Under **General Information**, copy the **Application ID** and paste it into `.env` as `DISCORD_APPLICATION_ID`.

### 2. Bot Token & Privileged Intents
1. In the left navigation, navigate to **Bot**.
2. Click **Reset Token**, copy the generated token, and paste it into `.env` as `DISCORD_BOT_TOKEN`.
3. Scroll down to **Privileged Gateway Intents** and enable:
   - ✅ **MESSAGE CONTENT INTENT** (*Mandatory* for reading slash command options).
   - ✅ **SERVER MEMBERS INTENT** (*Recommended* for role verification).
4. Click **Save Changes**.

### 3. OAuth2 Scopes & Bot Invite URL
1. Navigate to **OAuth2** -> **URL Generator**.
2. Select Scopes:
   - `bot`
   - `applications.commands`
3. Select Bot Permissions:
   - `View Channels`, `Send Messages`, `Send Messages in Threads`, `Create Public Threads`, `Embed Links`, `Attach Files`, `Read Message History`, `Use Application Commands`.
4. Calculated permission integer: `311922117632`.
5. Invite Link:
   ```text
   https://discord.com/api/oauth2/authorize?client_id=<YOUR_APPLICATION_ID>&permissions=311922117632&scope=bot%20applications.commands
   ```
6. Open the link in your browser and authorize the bot into the **MindHive** server.

### 4. Guild Instant Synchronization
1. Enable **Developer Mode** in Discord (`Settings -> Advanced -> Developer Mode`).
2. Right-click your MindHive server icon -> **Copy Server ID**.
3. Set in `.env`: `DISCORD_GUILD_ID=<copied_server_id>`.
4. When `agenthive.main` launches, all 9 slash commands will synchronize instantly to your guild within 2 seconds.

---

## 6. Supported Discord Slash Commands Reference

| Slash Command | Input Parameters | Execution Phase | Function |
| :--- | :--- | :--- | :--- |
| `/newproject` | `name: str`, `description: str` | Phase 1 | Creates workspace, generates `PROJECT.md`, registers Switch room. |
| `/project` | `project_id: str` | Phase 1 | Displays master specification and current status. |
| `/analyse` | `project_id: str` | Phase 4 | Dispatches independent parallel analyses across 4 agents. |
| `/discuss` | `project_id: str` | Phase 5 | Connects agents to Switch room for collaborative debate. |
| `/assign` | `project_id: str` | Phase 6 | Hermes synthesizes consensus, formulates WBS, displays approval buttons. |
| `/approve` | `project_id: str`, `task_code: str?` | Phase 7 | Sovereign Human Gate: unlocks tasks for sandboxed execution. |
| `/reject` | `project_id: str`, `reason: str` | Phase 7 | Sovereign Human Gate: aborts project proposal and logs rejection. |
| `/status` | `project_id: str` | Monitoring | Live status dashboard with agent and task states. |
| `/report` | `project_id: str` | Phase 8 | Executes approved tasks, runs unit tests, verifies Pony Tail compliance. |

---

## 7. Shutdown & Maintenance Procedures

### Clean Stack Shutdown
```bash
# Stop the AgentHive backend
pkill -f "agenthive.main"

# Stop the official Switch Docker containers (preserves database state)
docker compose -f docker-compose.switch.yml stop
```

### Full Teardown & Reset
```bash
# Stop containers and remove network bridges (preserves postgres volume)
docker compose -f docker-compose.switch.yml down

# If a completely fresh database is desired:
docker compose -f docker-compose.switch.yml down -v
```

### Health Check Verification Command
```bash
./venv/bin/pytest tests/test_switch_official.py -v
```
All 5 official Switch integration tests should pass in under 2 seconds.
