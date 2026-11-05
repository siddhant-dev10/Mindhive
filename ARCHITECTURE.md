# AgentHive — System Architecture Specification (`ARCHITECTURE.md`)

This document outlines the complete architectural design of **AgentHive**, a multi-agent AI collaboration platform. It details how independently operating frontier AI models communicate, challenge proposals, distribute tasks, and execute development under the supervision of **Hermes** and the sovereign authority of the human **Project Owner**.

---

## 1. End-to-End Architectural Flow

The foundational flow of AgentHive progresses through eight strictly coordinated stages:

```mermaid
flowchart TD
    %% Node Definitions
    PO([👤 Project Owner]):::humanStyle
    Discord[💬 Discord Interface]:::discordStyle
    AH_Engine[⚙️ AgentHive Core Orchestrator]:::coreStyle
    ProjDoc[📄 PROJECT.md Living Spec]:::storageStyle
    
    subgraph AnalysisPhase["Phase 2: Independent Analysis (Parallel Isolation)"]
        A_Codex[💻 Codex Analysis]:::agentStyle
        A_AGY[🚀 AGY Analysis]:::agentStyle
        A_Gemini[🧠 Gemini Analysis]:::agentStyle
    end

    subgraph DebatePhase["Phase 3 & 4: Switch Discussion Room & Hermes Supervision"]
        SwitchRoom[🔄 Switch Collaboration Room]:::switchStyle
        HermesSupervisor{👑 Hermes Supervision Engine}:::hermesStyle
    end

    subgraph ApprovalPhase["Phase 5: Human Sovereign Gate"]
        DiscordApproval[🛡️ Discord Approval Embed & Buttons]:::discordStyle
    end

    subgraph ExecutionPhase["Phase 6: Sandboxed Execution & Pony Tail"]
        DockerSandbox[📦 Ephemeral Docker Sandbox]:::sandboxStyle
        PonyTailEngine[✂️ Pony Tail Laziness Rules]:::sandboxStyle
        TestRunner[🧪 Automated Test Suite]:::sandboxStyle
    end

    subgraph DeliveryPhase["Phase 7: Final Reporting & Knowledge Commit"]
        FinalSummary[📋 Final Summary Report & Git Commit]:::storageStyle
    end

    %% Flow Connections
    PO -->|1. /agenthive create| Discord
    Discord -->|2. Webhook Event| AH_Engine
    AH_Engine -->|3. Scaffold Workspace & Generate| ProjDoc
    
    ProjDoc -.->|4. Parallel Read-Only Access| A_Codex
    ProjDoc -.->|4. Parallel Read-Only Access| A_AGY
    ProjDoc -.->|4. Parallel Read-Only Access| A_Gemini
    
    A_Codex -->|5. Post Initial Review| SwitchRoom
    A_AGY -->|5. Post Initial Review| SwitchRoom
    A_Gemini -->|5. Post Initial Review| SwitchRoom
    
    SwitchRoom <-->|6. Multi-Agent Debate & Cross-Examination| HermesSupervisor
    HermesSupervisor -->|7. Formulate Role & Task WBS| DiscordApproval
    
    DiscordApproval -->|8. Explicit Action: Approve / Modify / Reject| PO
    PO -->|9. Sign-off Event| DiscordApproval
    DiscordApproval -->|10. Dispatch Approved Plan| AH_Engine
    
    AH_Engine -->|11. Spin up Sandbox| DockerSandbox
    DockerSandbox --- PonyTailEngine
    DockerSandbox --> TestRunner
    TestRunner -->|12. Output & Diffs| HermesSupervisor
    
    HermesSupervisor -->|13. Compile Results & Update| FinalSummary
    FinalSummary -->|14. Post Delivery Embed| Discord
    Discord -->|15. Review Final Artifacts| PO

    %% Class Styles
    classDef humanStyle fill:#f9d5e5,stroke:#c83349,stroke-width:2px,color:#000;
    classDef discordStyle fill:#5865F2,stroke:#4752C4,stroke-width:2px,color:#fff;
    classDef coreStyle fill:#fcf4d9,stroke:#e6af2e,stroke-width:2px,color:#000;
    classDef storageStyle fill:#e0ece4,stroke:#66b2b2,stroke-width:2px,color:#000;
    classDef agentStyle fill:#d4eeff,stroke:#2b7bb9,stroke-width:2px,color:#000;
    classDef switchStyle fill:#ffdfba,stroke:#ff9a3c,stroke-width:2px,color:#000;
    classDef hermesStyle fill:#d0bdf4,stroke:#494ca2,stroke-width:2px,color:#000;
    classDef sandboxStyle fill:#ffe6eb,stroke:#e02401,stroke-width:2px,color:#000;
```

---

## 2. Overall System Architecture

AgentHive is designed around a decoupled, event-driven hexagonal architecture:

```mermaid
graph TB
    subgraph UI_Layer["1. Interface Layer"]
        D_Bot["Discord Bot / Interactions Gateway"]
        D_Slash["Slash Command Handlers (/agenthive)"]
        D_Components["Interactive Components (Buttons, Modals)"]
    end

    subgraph Transport_Layer["2. Collaboration & Transport Layer (Switch)"]
        Switch_Console["Switch Console (Desktop / Local Runner)"]
        Switch_Core["Switch Core Engine (Room Manager)"]
        Switch_MCP["Switch MCP Router (Trust & Tooling)"]
        Switch_Bridge["Discord-Switch Bidirectional Bridge"]
    end

    subgraph Orchestration_Layer["3. AgentHive Core Service (FastAPI)"]
        Event_Router["Async Event Router"]
        Workflow_Engine["State Machine & Phase Orchestrator"]
        Doc_Manager["PROJECT.md Manager (Atomic Git Sync)"]
        Budget_Governor["Token & Turn Budget Governor"]
    end

    subgraph Agent_Pool["4. Specialist Agent Adapters"]
        Codex_Adapter["Codex Adapter (OpenAI SDK / gpt-4o)"]
        AGY_Adapter["AGY Adapter (Antigravity CLI Subprocess)"]
        Gemini_Adapter["Gemini Adapter (Google GenAI SDK)"]
    end

    subgraph Supervision_Layer["5. Supervision Plane"]
        Hermes_Supervisor["Hermes Supervisor Agent (Nous Research)"]
        Conflict_Detector["Conflict & Deadlock Detector"]
        WBS_Generator["WBS & Task Allocator"]
    end

    subgraph Sandbox_Layer["6. Execution & Discipline Plane"]
        Docker_Daemon["Docker Sandbox Controller"]
        PonyTail_Guard["Pony Tail Enforcement Filter"]
        Ephemeral_Container["Scoped Ephemeral Container (cap-drop: ALL)"]
    end

    subgraph Data_Layer["7. Persistence Plane"]
        SQLite_Postgres[("SQLite / PostgreSQL Database")]
        Workspace_FS[("Project Workspace (Git Tracked)")]
    end

    %% Wiring
    UI_Layer <--> Switch_Bridge
    Switch_Bridge <--> Switch_Core
    Switch_Core <--> Switch_Console
    Switch_Core <--> Orchestration_Layer
    Orchestration_Layer <--> Agent_Pool
    Orchestration_Layer <--> Supervision_Layer
    Orchestration_Layer <--> Sandbox_Layer
    Orchestration_Layer <--> Data_Layer
    Sandbox_Layer --> Workspace_FS
```

---

## 3. Component Responsibilities

### 3.1 Discord Interface Layer
- Ingests slash commands (`/agenthive create`, `/agenthive status`, `/agenthive approve`).
- Renders rich embeds showing live project status, agent proposals, debate summaries, and logs.
- Captures human inputs via buttons and modals (Human-in-the-Loop gate).
- Manages dedicated project threads to prevent chatter spillover.

### 3.2 Switch Collaboration Layer (`sandbox-quantum/switch`)
- Provides shared "Rooms" where agents and humans collaborate within a unified conversational history.
- Handles multi-agent routing, message queues, and distinct avatar/identity presentation.
- Interfaces with the local Switch Console for on-demand local session spinning.
- Exposes Model Context Protocol (MCP) servers for system metrics and tool invocations.

### 3.3 AgentHive Core Orchestrator (FastAPI)
- Drives the 8-phase workflow state machine.
- Manages asynchronous event streams between Switch, Discord, and model backends.
- Enforces token budgets and max conversation turns to eliminate infinite debate loops.
- Provides REST APIs and OpenAPI definitions for programmatic management.

### 3.4 Document Manager (`PROJECT.md`)
- Generates standardized project specifications from `PROJECT_TEMPLATE.md`.
- Maintains strict atomic writes and Git commit tracking on every specification change.
- Exposes read-only views to agents during the independent analysis phase.

### 3.5 Agent Adapter Pool
- **ChatGPT Codex Adapter:** Formulates architecture, schema models, and writes core backend code.
- **AGY Adapter:** Runs Antigravity CLI diagnostic tools, evaluates integration feasibility, and assists in terminal workflows.
- **Gemini Adapter:** Conducts deep research, cross-examines proposed stacks, and designs verification/test suites.

### 3.6 Hermes Supervisory Engine
- Moderates agent debates, flags logical contradictions, and terminates circular arguments.
- Synthesizes disparate proposals into a unified Work Breakdown Structure (WBS).
- Dynamically assigns tasks based on agent specialization.
- Escalates architectural forks or ambiguous requirements directly to the Project Owner.

### 3.7 Execution & Pony Tail Sandbox
- Executes approved code tasks inside isolated, ephemeral Docker containers.
- Implements Pony Tail rules to prune over-engineered abstractions and block unauthorized external packages.
- Executes automated test runners and returns structured diffs to Hermes.

### 3.8 Persistence Layer
- **SQLite / PostgreSQL:** Stores relational state, session IDs, turn counters, audit trails, and execution logs.
- **Workspace Filesystem:** Local disk repository containing code, test files, and `PROJECT.md`, tracked by Git.

---

## 4. Agent Communication Architecture

AgentHive separates communication into two distinct planes:
1. **Public Collaboration Plane (Switch Room):** An open, multi-agent channel where messages are broadcast to all participants (Codex, AGY, Gemini, Hermes, and human observers). This is mirrored into a Discord thread.
2. **Private Control Plane (AgentHive Internal Bus):** Asynchronous direct RPCs between the AgentHive Orchestrator and individual agent adapters (used for independent analysis, private health checks, and sandboxed code execution prompts).

```mermaid
sequenceDiagram
    autonumber
    participant AH as AgentHive Engine
    participant Bus as Switch Event Bus
    participant C as Codex
    participant A as AGY
    participant G as Gemini
    participant H as Hermes

    Note over AH,G: Phase 2: Private Control Plane
    AH->>C: Direct RPC: Analyze PROJECT.md (Isolation)
    AH->>A: Direct RPC: Analyze PROJECT.md (Isolation)
    AH->>G: Direct RPC: Analyze PROJECT.md (Isolation)
    C-->>AH: Analysis Payload
    A-->>AH: Analysis Payload
    G-->>AH: Analysis Payload

    Note over Bus,H: Phase 3 & 4: Public Collaboration Plane
    AH->>Bus: Open Room: #project-alpha-discussion
    AH->>Bus: Broadcast: "Independent Analysis Completed. Begin Discussion."
    C->>Bus: Post: Architecture & Tech Stack Proposal
    G->>Bus: Challenge: "Why PostgreSQL over SQLite? Here is the latency trade-off..."
    A->>Bus: Propose: "AGY diagnostic check confirms SQLite suffices with WAL mode."
    C->>Bus: Concur: "Accepted, updating schema to SQLite."
    H->>Bus: Intervene: "Consensus reached on SQLite. Moving to Task Allocation."
```

---

## 5. Session & State Management

AgentHive models every project as a deterministic Finite State Machine (FSM). State transitions are governed by strict pre-conditions:

```mermaid
stateDiagram-v2
    [*] --> DRAFT: Project Created in Discord
    DRAFT --> INDEPENDENT_ANALYSIS: PROJECT.md Generated
    INDEPENDENT_ANALYSIS --> IN_DISCUSSION: All 3 Agent Reviews Submitted
    IN_DISCUSSION --> PROPOSAL_SYNTHESIS: Consensus Reached OR Turn Limit Reached
    PROPOSAL_SYNTHESIS --> PENDING_APPROVAL: Hermes Generates WBS Embed
    
    PENDING_APPROVAL --> IN_DISCUSSION: PO Clicks "Request Revisions"
    PENDING_APPROVAL --> REJECTED: PO Clicks "Reject"
    PENDING_APPROVAL --> EXECUTION_ACTIVE: PO Clicks "Approve"
    
    EXECUTION_ACTIVE --> VERIFICATION: Docker Tasks Complete
    VERIFICATION --> EXECUTION_ACTIVE: Tests Fail (Bug-squashing loop < 3)
    VERIFICATION --> COMPLETED: Tests Pass & PO Sign-off
    
    REJECTED --> [*]
    COMPLETED --> [*]
```

### State Storage Details:
- Every transition emits an event to the relational database (`projects` table).
- Project states are recoverable upon service restart: if the orchestrator restarts while in `IN_DISCUSSION`, it queries the Switch Room message history and resumes the session without losing context.

---

## 6. Database Schema Requirements

AgentHive utilizes a relational schema optimized for auditability, session recovery, and task tracking:

```mermaid
erDiagram
    PROJECTS ||--o{ AGENT_SESSIONS : contains
    PROJECTS ||--o{ DISCUSSIONS : logs
    PROJECTS ||--o{ TASKS : divides_into
    TASKS ||--o{ TASK_LOGS : generates

    PROJECTS {
        uuid id PK
        string name
        string discord_guild_id
        string discord_channel_id
        string discord_thread_id
        string switch_room_id
        string current_state
        string project_md_path
        timestamp created_at
        timestamp updated_at
    }

    AGENT_SESSIONS {
        uuid id PK
        uuid project_id FK
        string agent_name
        string provider
        string model_identifier
        int prompt_tokens_used
        int completion_tokens_used
        string status
    }

    DISCUSSIONS {
        uuid id PK
        uuid project_id FK
        int turn_number
        string sender_agent
        text message_content
        string reply_to_agent
        timestamp timestamp
    }

    TASKS {
        uuid id PK
        uuid project_id FK
        string title
        text description
        string assigned_agent
        string status
        boolean human_approved
        string branch_name
        timestamp created_at
    }

    TASK_LOGS {
        uuid id PK
        uuid task_id FK
        text stdout
        text stderr
        int exit_code
        string diff_patch
        timestamp executed_at
    }
```

---

## 7. Error Handling, Fault Tolerance & Recovery

### 7.1 Agent Crash or Timeout
- **Detection:** Each adapter implements an exponential backoff with a hard timeout of 60 seconds per turn.
- **Recovery:** If an agent (e.g. Codex) fails to respond after 2 retries, Hermes receives a `ProviderDegraded` alert. Hermes can re-route the prompt to an alternate model (e.g. Gemini 1.5 Pro) or alert the Project Owner via Discord.

### 7.2 Infinite Debate Prevention (Turn & Token Governance)
- **Problem:** Agents may engage in endless philosophical debates without reaching an implementation consensus.
- **Mitigation:**
  1. **Hard Turn Cap:** Maximum 10 turns per discussion round.
  2. **Sentiment & Drift Heuristics:** Hermes monitors semantic similarity between rounds. If delta is < 5% across 2 consecutive rounds, Hermes forcibly locks the discussion and triggers synthesis.
  3. **Token Governor:** Hard cap of 100,000 tokens per discussion session.

### 7.3 Sandboxed Execution Failures
- **Compilation/Syntax Errors:** Captured by the Docker runner and returned to the responsible agent with the exact stderr output.
- **Bug-Squashing Loop Limit:** Maximum 3 automatic fix attempts. If tests still fail after 3 attempts, Hermes halts execution and posts a high-priority escalation embed to Discord with logs.
- **Host Protection:** Ephemeral containers have no access to host networks, environment secrets, or directories outside the designated `/workspace/output`.
