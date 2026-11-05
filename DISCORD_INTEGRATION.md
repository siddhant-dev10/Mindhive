# AgentHive — Discord User Interface Specification (`DISCORD_INTEGRATION.md`)

This document defines the Discord integration architecture, channel taxonomy, slash commands, interactive UI components, webhook routing, and permission models that power **AgentHive**'s human-in-the-loop control plane.

---

## 1. Architectural Role of Discord

Discord serves as the primary window into the AgentHive swarm. While the agents interact, deliberate, and test inside the Switch platform and Docker sandboxes, the human **Project Owner** monitors, guides, and governs the entire system directly from Discord on desktop or mobile.

```mermaid
graph TD
    PO([👤 Human Project Owner]) <--> Discord[💬 Discord Server]
    
    subgraph DiscordChannels["Discord Guild Architecture"]
        Lounge["#agenthive-lounge\n(Slash Commands & System Alerts)"]
        WarRoom["#project-war-room (Thread)\n(Live Switch Room Mirror)"]
        ApprovalChan["#project-approvals\n(Interactive Human Gates)"]
        LogsChan["#project-logs\n(Live Build, Test & Git Stream)"]
    end

    Discord --> Lounge
    Discord --> WarRoom
    Discord --> ApprovalChan
    Discord --> LogsChan

    subgraph AgentHive_Backend["AgentHive Discord Gateway"]
        SlashRouter["Slash Command Handler (/agenthive)"]
        InteractiveHandler["Button & Modal Callback Handler"]
        WebhookBroadcaster["Switch Webhook Broadcaster"]
    end

    Lounge <--> SlashRouter
    WarRoom <--> WebhookBroadcaster
    ApprovalChan <--> InteractiveHandler
    LogsChan <-- WebhookBroadcaster
```

---

## 2. Discord Channel Architecture

To keep multi-agent chatter organized and prevent cognitive overload, AgentHive segregates activity into structured channels:

| Channel / Thread | Scope & Audience | Content & Primary Activities |
|---|---|---|
| **`#agenthive-lounge`** | Server-wide (All Members) | Bot onboarding, global `/agenthive create` commands, project launch announcements, high-level milestone notifications. |
| **`#project-<slug>-war-room`** *(Thread)* | Project Owner & Agent Swarm | Real-time mirror of the Switch Room. Displays the multi-agent debate between Codex, AGY, Gemini, and Hermes. |
| **`#project-<slug>-approvals`** | Project Owner & Hermes | Dedicated channel for Human-in-the-Loop decision gates. Rich embeds with interactive buttons (`Approve`, `Request Revisions`, `Reject`). |
| **`#project-<slug>-logs`** | Technical Observers & PO | Read-only stream of Docker container execution, test results, Git commit diffs, and linting checks. |

---

## 3. Slash Command Specifications

AgentHive registers Discord application slash commands under the `/agenthive` root namespace:

### 3.1 `/agenthive create`
- **Description:** Initializes a new multi-agent project workspace and launches the collaborative lifecycle.
- **Options:**
  - `name` *(string, required)*: Slugified project name (e.g. `fast-cache`, `auth-proxy`).
  - `idea` *(string, required)*: Detailed description of project goals, features, and constraints.
  - `template` *(choice, optional)*: Default `general_software`, `cli_tool`, `web_api`, `microservice`.
- **Response:** Ephemeral acknowledgement followed by an interactive rich embed linking to the project's dedicated channels.

### 3.2 `/agenthive status`
- **Description:** Displays real-time progress, active phase, token expenditure, and active agent states.
- **Options:**
  - `project_id` *(string, optional)*: Defaults to the project bound to the current thread.
- **Response:** Rich status dashboard embed.

### 3.3 `/agenthive approve`
- **Description:** Programmatically sign off on the active proposal (equivalent to clicking the Discord button).
- **Options:**
  - `task_id` *(string, optional)*: Approves specific task or full WBS if omitted.

### 3.4 `/agenthive pause`
- **Description:** Emergency freeze on all agent debates and containerized execution tasks.
- **Options:**
  - `reason` *(string, required)*: Explanatory note stored in the project audit log.

### 3.5 `/agenthive summarize`
- **Description:** Requests Hermes to immediately compile and output the current project state and progress.

---

## 4. Interactive Components & Visual Wireframes

### 4.1 Work Breakdown Structure Approval Embed
When Hermes concludes synthesis, it posts an interactive component embed to `#project-<slug>-approvals`:

```text
+----------------------------------------------------------------------------------+
|  🐝 AGENTHIVE — PROPOSAL APPROVAL REQUIRED                                       |
|  Project: LogStream | Status: PENDING_APPROVAL | Round: 1                        |
+----------------------------------------------------------------------------------+
|  Hermes has moderated the debate and formulated the final task matrix:           |
|                                                                                  |
|  📋 Architecture Consensus:                                                      |
|  • In-memory ring buffer (deque) with reverse tag indexing                       |
|  • Bounded regex queries with 50ms evaluation deadline                           |
|  • 100% Python standard library (Zero pip packages)                              |
|                                                                                  |
|  🔨 Proposed Work Breakdown Structure (WBS):                                     |
|  [TASK-01] Codex  -> Ring Buffer & Tag Store (src/engine.py)                     |
|  [TASK-02] Codex  -> Protected Regex Query Engine (src/query.py)                 |
|  [TASK-03] AGY    -> CLI Ingestion Harness & Dockerfile (src/cli.py)             |
|  [TASK-04] Gemini -> ReDoS Test Matrix & Benchmarks (tests/test_stream.py)       |
|                                                                                  |
|  Estimated Execution Duration: ~2 minutes inside sandboxed containers            |
+----------------------------------------------------------------------------------+
|  [  ✅ Approve & Run  ]    [  ✏️ Request Revisions  ]    [  ❌ Abort Project  ]   |
+----------------------------------------------------------------------------------+
```

### 4.2 Interactive Button Handlers:
- **`Approve & Run` (Green / Success):**
  - Disables button row.
  - Updates embed color to green.
  - Emits `task.approved` event.
  - Triggers Docker sandbox provisioning.
- **`Request Revisions` (Gray / Secondary):**
  - Pops open a Discord Modal Form:
    ```text
    +--------------------------------------------------------+
    |  AgentHive: Architectural Revision Request             |
    +--------------------------------------------------------+
    |  Provide instructions or constraints for the agents:   |
    |  [ Change buffer maxlen to 100,000 items and add ... ] |
    |                                                        |
    |  [ Submit Changes ]                                    |
    +--------------------------------------------------------+
    ```
  - Submits the feedback directly back into the Switch room as a Project Owner directive.
- **`Abort Project` (Red / Danger):**
  - Aborts the project, archives the thread, and locks the workspace.

---

## 5. Webhook & Agent Identity Rendering

To give each agent a distinct presence in the Discord war room, AgentHive leverages Discord Webhooks dynamically:

| Participant | Display Name | Custom Avatar Asset | Primary Message Tone |
|---|---|---|---|
| **Hermes** | `Hermes (Supervisor)` | `assets/avatars/hermes.png` (Gold/Purple Helm) | Authoritative, structured, synthesizing |
| **Codex** | `ChatGPT Codex` | `assets/avatars/codex.png` (Teal Terminal) | Technical, architectural, code-focused |
| **AGY** | `AGY (Antigravity)` | `assets/avatars/agy.png` (Orange Jetpack) | Pragmatic, tooling-oriented, diagnostic |
| **Gemini** | `Google Gemini` | `assets/avatars/gemini.png` (Blue Spark) | Analytical, inquiring, test-driven |

AgentHive manages a pool of Discord Webhook tokens scoped to the project channels, injecting custom avatars and names on a per-message basis.

---

## 6. Permissions & Bot Scopes

### Discord OAuth2 Scopes:
- `bot`
- `applications.commands`

### Required Bot Permissions:
- `View Channels` (`VIEW_CHANNEL`)
- `Send Messages` (`SEND_MESSAGES`)
- `Create Public Threads` (`CREATE_PUBLIC_THREADS`)
- `Send Messages in Threads` (`SEND_MESSAGES_IN_THREADS`)
- `Manage Webhooks` (`MANAGE_WEBHOOKS`)
- `Embed Links` (`EMBED_LINKS`)
- `Attach Files` (`ATTACH_FILES`)
- `Read Message History` (`READ_MESSAGE_HISTORY`)

### Rate-Limit Management:
Discord enforces a 5-message-per-second rate limit per channel/webhook. The AgentHive Discord Gateway incorporates a token-bucket queue:
- Outgoing agent debate messages are throttled to a minimum delay of 1.2 seconds between messages.
- This prevents Discord 429 rate-limit errors and produces a natural, readable conversational cadence for human observers.
