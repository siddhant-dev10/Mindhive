# MindHive Conversational Demo Runbook
## Autonomous Multi-Agent Engineering Manager Powered by Google Gemini & Official Switch

This runbook guides hackathon presenters and operators through a live, end-to-end demonstration of MindHive.

---

## 1. Demonstration Scenario Summary

In this demonstration, you will show how MindHive acts as an **autonomous AI Engineering Manager**:
1. Connects to and inspects a GitHub repository without executing untrusted code.
2. Identifies architecture, tech stack, entry points, and technical debt with exact file citations.
3. Coordinates a multi-agent debate among **ChatGPT Codex**, **Antigravity AGY**, **Google Gemini**, and **Nous Hermes** over the **Official Switch Protocol**.
4. Synthesizes an actionable Work Breakdown Structure (WBS) development plan.
5. Strictly enforces the **Sovereign Human Approval Gate** before any task is executed.
6. Executes approved tasks inside an **isolated non-root container runner** and delivers a verified audit report.

---

## 2. Pre-Flight Checklist

Before presenting, ensure the following services are active:

| Component | Target URL / Port | Check Command |
| :--- | :--- | :--- |
| **Official Switch Core** | `http://127.0.0.1:8080` (or `8082`) | `curl -s http://127.0.0.1:8080/health \| jq .` |
| **PostgreSQL (Switch DB)** | `127.0.0.1:5433` | `docker ps \| grep switch-postgres` |
| **MindHive Backend** | `http://127.0.0.1:8000` | `curl -s http://127.0.0.1:8000/api/health \| jq .` |
| **Discord Gateway** | Connected to Discord Guild | Look for "AgentHive Discord Bot logged in" in logs |
| **Isolated Docker Runner** | Docker daemon available | `docker images \| grep agenthive-test-docker_sec_ws` |

### Environment Variables (.env)
```bash
GEMINI_API_KEY=your_live_google_gemini_api_key
DISCORD_BOT_TOKEN=your_live_discord_bot_token
DISCORD_OWNER_ID=your_discord_user_id
GITHUB_TOKEN=your_github_fine_grained_pat (optional for public repos)
SWITCH_MODE=official
SWITCH_CORE_URL=http://127.0.0.1:8080
```

---

## 3. Live Demonstration Script (Step-by-Step)

### Step 1: Conversational Greeting & Persona Introduction
In your Discord server channel (or via direct message), type:
```text
@AgentHive hello
```
*(Or use `/ask query: "hello"`)*

**Expected Result:**
MindHive introduces itself as an autonomous AI Engineering Manager coordinating Codex, AGY, Gemini, and Hermes over Official Switch. It displays live runtime statuses for the Switch Core and Gemini model.

---

### Step 2: Codebase Understanding & Architectural Inspection
Ask MindHive to inspect the codebase:
```text
@AgentHive analyse https://github.com/openai/whisper
```
*(Or for the local project: `@AgentHive what does this project do?`)*

**Expected Result:**
MindHive performs a secure, read-only analysis without executing downloaded code. It returns:
- **Project Identity:** Purpose, problem solved, and intended users.
- **Technical Architecture:** Languages, frameworks, and entry points.
- **Engineering Assessment:** Observed working capabilities and missing infrastructure/tests.
- **File Citations:** References specific files like `README.md`, `requirements.txt`, or `setup.py`.

---

### Step 3: Natural Follow-Up Technical Q&A
Ask a contextual follow-up question:
```text
@AgentHive what are the main security concerns or technical debt in this project?
```

**Expected Result:**
MindHive's Gemini conversational coordinator uses multi-turn session memory and the active repository context to answer directly, highlighting credential isolation, origin protections, or missing CI pipelines.

---

### Step 4: Multi-Agent Collaboration over Official Switch
Instruct MindHive to coordinate a development plan:
```text
@AgentHive create a development plan
```

**Expected Result:**
1. MindHive creates an isolated project and registers a dedicated **Switch War Room**.
2. Independent analyses run across the agent swarm:
   - **Codex:** Evaluates code implementation and algorithms.
   - **AGY:** Audits infrastructure, security boundaries, and container sandboxing.
   - **Gemini:** Audits quality assurance, documentation, and testing.
   - **Hermes:** Moderates the debate as supervisor.
3. The agents engage in bounded multi-agent debate over **Official Switch Core**.
4. Hermes synthesizes the discussion into a prioritized **Work Breakdown Structure (WBS)** with assigned agents, acceptance criteria, and dependencies.

---

### Step 5: Sovereign Human Approval Gate
Point out the approval gate to judges:
- Emphasize: **"Notice that NO code has been executed yet. MindHive does not autonomously touch production or run arbitrary scripts without human sign-off."**
- In Discord, two interactive buttons are displayed:
  - `[✅ Approve Plan]`
  - `[❌ Reject Plan]`

Click **`Approve Plan`** *(or run `/approve <project_id>`)*.

**Expected Result:**
The button state updates, and MindHive confirms:
`✅ Sovereign Human Authorization Granted. Tasks unlocked for execution.`

---

### Step 6: Isolated Non-Root Execution & Verification
Execute the approved tasks and generate the final report:
```text
/report project_id: <project_id>
```

**Expected Result:**
1. Tasks are dispatched to an isolated, non-root, network-disabled Docker container runner (`agenthive-test-docker_sec_ws:latest`).
2. Generated changes are tested and audited against the **Pony Tail** standard (dependency minimalism and test passes).
3. MindHive replies with the rich delivery report embed showing:
   - Execution status: `VERIFIED`
   - Pony Tail audit status: `PASSED`
   - Test results: `SUCCESS`
   - Tasks executed count and generated artifacts.

---

### Step 7: Live Web Dashboard Verification
Open `http://localhost:8000/dashboard` in a browser:
- Log in using your configured dashboard credentials.
- Observe real-time Server-Sent Events (SSE) streaming task state transitions.
- Inspect the Switch discussion transcript, agent provenance badges, and execution diffs.

---

## 4. Judging Criteria Mapping

| Judging Criterion | Weight | How MindHive Demonstrates It |
| :--- | :--- | :--- |
| **Switch Usage** | **30%** | Official Switch Core is the central nervous system. Agents register genuine sessions, exchange structured events, and record verifiable event IDs in the database. |
| **Technical Execution** | **25%** | Production-ready asynchronous stack (FastAPI, Discord.py 2.x, Google Gen AI SDK), strict non-root container isolation, path traversal guards, and zero-defect test suite (88 passed). |
| **Creativity & Impact** | **25%** | Transforms autonomous agents from toys into an enterprise-grade AI Engineering Manager. Real human-in-the-loop governance guarantees safety. |
| **Presentation** | **20%** | Conversational Discord interface (`@AgentHive` & `/ask`), interactive UI buttons, rich embeds, and live web dashboard with real-time SSE streaming. |

---

## 5. Troubleshooting & Resilience Fallbacks

- **Gemini API Unreachable or Rate Limited:**
  MindHive automatically switches to deterministic codebase explanations (`explain_codebase_deterministic`). It clearly labels its runtime state without crashing or hallucinating.
- **Switch Core Offline:**
  MindHive falls back to local protocol mode with explicit local runtime evidence labels (`local fallback`).
- **Discord Bot Mentions Blocked by Permissions:**
  Use the `/ask` slash command as an identical alternative.
- **Non-Owner Attempts to Plan or Approve:**
  MindHive immediately responds: `⛔ Authorization Denied: Only the configured MindHive project owner can initiate a development workflow.`
