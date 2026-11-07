# AGENTHIVE V2 — MINDHIVE LIVE ACTIVATION GUIDE

## Current startup guidance — 2026-11-07

This guide contains historical startup notes. Use `DEPLOYMENT.md` as the current source for a clean local API start and Switch Compose limits. The repository Compose templates describe a new stack and must not be applied to the existing external `test_official_switch` stack or its Docker volume without an approved migration and verified backup/restore. The updated backend has not been started, and task execution remains blocked until an isolated native-agent runner is implemented.

**Target Guild:** MindHive (`1567933462575325375`)  
**Target Channel:** `#general` / Lounge (`1567933463120842765`)  
**Application ID:** `1568557236626792498`  
**Saved Permission Integer:** `309237763072`  
**Document:** `MINDHIVE_STARTUP_GUIDE.md`  
**Date:** November 7, 2026  

---

## 1. Current Verified Status

| Component | Status | Notes |
| :--- | :---: | :--- |
| **MindHive Server Installation** | **CONFIRMED** | Bot user is added to MindHive with App badge. |
| **MindHive Gateway Connection** | **ONLINE** | Shard connected (Session `60771390da...`). All 9 slash commands registered. |
| **Official Switch Core** | **HEALTHY** | Running via Docker on `127.0.0.1:8080`; PostgreSQL on `127.0.0.1:5433`. |
| **AgentHive Backend** | **LIVE** | Running via uvicorn on `0.0.0.0:8000` with SQLite WAL database. |

---

## 2. Secure Local Entry Procedure for Bot Token

> [!CAUTION]
> **Zero-Leakage Security Protocol:**
> - Never paste, print, log, or commit your Discord Bot Token in chat, issue trackers, or version control.
> - `.gitignore` is configured to ignore `.env` and all credential patterns.

### Step 1: Obtain the Bot Token from Discord Developer Portal
1. Open your browser and navigate directly to:
   **[https://discord.com/developers/applications/1568557236626792498/bot](https://discord.com/developers/applications/1568557236626792498/bot)**
2. Click **Reset Token** (or copy existing token if displayed).
3. Confirm that **Message Content Intent** is toggled **ON** under Privileged Gateway Intents.

### Step 2: Locally Insert the Token into `.env`
In your terminal on the host machine, run:
```bash
cd /Users/sidh._./mindhive
```
Open `.env` in your local text editor, or run this interactive prompt (which will not echo the token to terminal history):
```bash
read -s -p "Enter DISCORD_BOT_TOKEN: " token && sed -i '' "s|^DISCORD_BOT_TOKEN=.*|DISCORD_BOT_TOKEN=$token|" .env && unset token
```

---

## 3. Single-Command System Startup

Once the token is in `.env`, start the complete integrated stack:

### Step 1: Ensure Official Switch Containers are Up
```bash
cd /Users/sidh._./mindhive
docker compose -f docker-compose.switch.yml up -d
```
Verify readiness:
```bash
curl -s http://127.0.0.1:8080/health/ready
```

### Step 2: Start AgentHive Backend & Live Discord Gateway
```bash
cd /Users/sidh._./mindhive
./venv/bin/python -m uvicorn agenthive.main:app --host 127.0.0.1 --port 8000
```

---

## 4. Live Gateway & Guild Verification Checklist

When the backend starts with `DISCORD_BOT_TOKEN` populated:

1. **Gateway Login:** Terminal logs will display:
   ```text
   INFO: AgentHive Discord Bot logged in as AgentHive#5421 (ID: ...)
   INFO: Connected to 1 guild(s): MindHive
   INFO: Synchronized 9 Discord slash commands to Guild ID: 1567933462575325375
   ```
2. **Online Status:** In the MindHive Discord server member list, the **AgentHive** bot badge changes from **Offline** to **Online** with status `Watching Agent Swarm | /newproject`.
3. **Slash Commands:** In `#general` (or `#agenthive-lounge`), type `/` to see all 9 registered commands:
   - `/newproject`
   - `/project`
   - `/analyse`
   - `/discuss`
   - `/assign`
   - `/approve`
   - `/reject`
   - `/status`
   - `/report`

---

## 5. Live Demonstration via Discord

In the MindHive Discord channel, execute this command sequence:

1. **Intake:**
   ```text
   /newproject name:CacheFlow description:High-throughput pure-standard-library in-memory cache with TTL support and zero pip dependencies
   ```
   *The bot generates `PROJECT.md`, registers a Switch war room, and creates a public thread.*

2. **Analysis:**
   ```text
   /analyse project_id:<project_id>
   ```
   *Dispatches independent parallel analyses across Codex, AGY, Gemini, and Hermes.*

3. **Discussion:**
   ```text
   /discuss project_id:<project_id>
   ```
   *Conducts multi-turn collaboration in the Switch room and renders the debate.*

4. **Task Proposal:**
   ```text
   /assign project_id:<project_id>
   ```
   *Hermes generates the WBS and attaches interactive `[ ✅ Approve & Run ]` and `[ ❌ Reject ]` buttons.*

5. **Human Gate Signoff:**
   Click `[ ✅ Approve & Run ]` (or type `/approve project_id:<project_id>`).
   *Executes sandboxed tasks across Codex, AGY, and Gemini.*

6. **Delivery & Retrospective:**
   ```text
   /report project_id:<project_id>
   ```
   *Verifies 100% Pony Tail standard-library compliance, runs unit tests, and outputs final report.*

## Live readiness caveat (2026-11-07)

The installed Discord bot was observed Offline. Startup instructions do not establish gateway authentication. Before demonstration, configure `DISCORD_OWNER_ID` locally, start/restart the API, and confirm `/api/status` reports Discord online and command sync evidence. Current full test run: 45 passed in 826.18s. Current final verdict remains **NOT READY** until live criteria are demonstrated.


## Mission completion evidence — 2026-11-07 (supersedes earlier runtime caveats)

### Verified live state

- Discord Developer Portal configuration was already saved. MindHive `/general` visibly showed “Siddhant has added AgentHive App to the server.” The AgentHive member entry was subsequently Online. The live gateway authenticated as bot `1568557236626792498`, connected to one guild, and logged synchronization of all 9 guild slash commands for `1567933462575325375`.
- Verified identifiers: Application ID `1568557236626792498`; Bot ID `1568557236626792498` (gateway login identity); Guild ID `1567933462575325375`; General channel ID `1567933463120842765`; owner user ID `1027116327997034496` (copied from the owner context menu with Developer Mode already on).
- Saved invite permission integer: `309237763072`; scopes `bot applications.commands`; requested permissions were View Channels, Send Messages, Embed Links, Attach Files, Read Message History, Create Public Threads, and Send Messages in Threads. Manage Messages and Administrator remain excluded. Message Content intent is on; Server Members and Presence intents are off. Effective per-channel overwrites were not independently inspected.
- `.env` was updated with `DISCORD_OWNER_ID=1027116327997034496`; file permissions remain `0600`. No token or API key was read, printed, copied, or changed.
- Official Switch Core readiness returned `ready`; PostgreSQL was healthy. Four AgentHive identities registered successfully, held SSE event streams, and received heartbeats. This verifies infrastructure connections, not successful shared-room message delivery.
- `/api/status` after startup reported Discord online, one guild, 9 commands, owner configured, Switch official/online and four agent connections. Status was `degraded` because Gemini was local fallback and not a live API runtime.

### Live Discord acceptance project

- Created through MindHive `/newproject`: `AgentHive Live Acceptance 2026-11-07`, ID `e1cd86bf-e4f5-4a7d-a074-f9cc3a259ff0`, workspace `workspaces/agenthive-live-acceptance-2026-11-07-e1cd86/`. The bot created `PROJECT.md` and a Discord war-room thread.
- `/analyse` returned four proposal cards. Codex native CLI session IDs appeared in runtime logs. AGY’s CLI was available but emitted a headless command-permission prompt and fell back; Gemini used the local QA engine; Hermes identified itself as standalone governance mode. These are not four live remote agents.
- `/discuss` returned four turns. Codex’s own turn states it could not post to the Switch room. Inspection of `run_switch_discussion()` confirms the debate was assembled and persisted locally without posting through the official Switch client. The official Switch service therefore did not deliver this discussion between agents, despite the Discord embed wording.
- `/assign` produced three tasks. Discord displayed the approval gate and then recorded an interactive approval attributed to `Siddhant`. The bot ran `/report`, posted COMPLETED, and reported an earlier four-test pass. The live approval event is visible in `#general`; project state and task records are persisted in SQLite.
- The generated source was inspected. The initial test set did not detect a stale tag-index growth bug and treated regex queries as potentially unbounded. I fixed the sample implementation to evict stale tag IDs and to do bounded literal searches, then ran the generated project’s actual command `PYTHONPATH="$PWD/workspaces/agenthive-live-acceptance-2026-11-07-e1cd86" ./venv/bin/python -m unittest discover -s workspaces/agenthive-live-acceptance-2026-11-07-e1cd86/tests`: exit 0, **7 tests passed**.
- The execution log also recorded a Codex CLI timeout (50 seconds) during task execution. Treat the posted report’s blanket “all approved tasks executed” claim as overstated: generated files and passing tests are verified, but complete native execution by every assigned agent is not.

### Code fixes and tests

- Fixed official Switch agent-name slugification while preserving friendly display labels; before the fix, Switch rejected names containing spaces/capitals. All four official registrations subsequently returned HTTP 200 and SSE/heartbeat requests succeeded.
- Replaced hardcoded `/api/status` readiness claims with live gateway, command-sync, Switch health/connection, and agent runtime-mode data. Its healthy verdict now requires the owner ID and live Gemini API as well as the connected gateway/Switch.
- Tightened approval controls: Discord `/approve`, `/reject`, `/report` and interactive buttons require the configured owner; server administrator status no longer substitutes. The dashboard’s unauthenticated approve/reject/execute endpoints now return 403, and dashboard buttons direct the user to owner-authenticated Discord commands.
- Full repository suite: `./venv/bin/pytest tests/ -q` — exit 0, **45 passed in 826.18s**; rerun after the initial runtime integration changes — exit 0, **45 passed in 840.61s**. After owner-only controls were tightened: `./venv/bin/pytest tests/test_discord_gateway.py -q` — exit 0, **11 passed in 161.08s**. It includes owner-only interactive approval and 403 checks for dashboard approve/reject/execute routes. Two existing FastAPI `on_event` deprecation warnings were emitted. `py_compile` succeeded on changed Python modules.

### Remaining blockers and verdict

- **NOT READY.** Gemini API key is missing; Hermes daemon is disconnected; AGY’s native execution needs an interactive command approval that headless execution cannot provide; Codex timed out during task execution.
- Switch connections are real, but `/discuss` did not create/post messages through official Switch room APIs; the exchange is local orchestration text. Shared cross-agent delivery, official room subscriptions and recovery remain unverified.
- Dashboard renders real project/status APIs, but `agenthive/ui/app.js` still contains hardcoded supervision architecture text and lacks complete live event/runtime panels. Approval and execution are intentionally directed through authenticated Discord commands.
- A pre-existing AGY process was found using the prohibited `--dangerously-skip-permissions` flag. It was not started or stopped during this mission. Owner should inspect and stop it before relying on AGY.
- During this authorized work, tests and the live acceptance run created database test records; they were preserved. Latest observed API status showed 143 projects and 144 tasks. No database or workspace was deleted.
- The Discord bot is installed and was authenticated/online during the demonstration; this does not establish that it remains online after the current process is stopped. Current deployment is the local uvicorn session and the existing Switch/PostgreSQL containers.
